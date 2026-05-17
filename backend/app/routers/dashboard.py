"""ダッシュボード・ヘルス・ユニバースAPI"""
import os
from fastapi import APIRouter
from app.services.screener import get_progress
from app.services.price_fetcher import get_usd_jpy, is_sample_mode
from app.database import get_db_info
from app.db_repo import latest_job
from app.utils import clean_for_json

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/health")
def health_check():
    db_info = get_db_info()
    return {
        "status": "ok",
        "environment": os.getenv("APP_ENV", "local"),
        "database": "connected",
        "database_type": db_info.get("url_scheme"),
        "sample_mode": is_sample_mode(),
        "message": "短期急騰3000円以下AIスクリーナー バックエンド稼働中",
    }


@router.get("/dashboard")
def get_dashboard():
    p = get_progress()
    results = p.get("results", [])
    exclusions = p.get("exclusions", [])
    all_count = len(results) + len(exclusions)

    classification_counts = {}
    for r in results:
        cls = r.get("classification", "不明")
        classification_counts[cls] = classification_counts.get(cls, 0) + 1

    vol_cycle_counts = {}
    for r in results:
        vc = r.get("volume_cycle_state", "不明")
        vol_cycle_counts[vc] = vol_cycle_counts.get(vc, 0) + 1

    chart_cycle_counts = {}
    for r in results:
        cc = r.get("chart_cycle_state", "不明")
        chart_cycle_counts[cc] = chart_cycle_counts.get(cc, 0) + 1

    warning_flag_counts = {}
    for r in results:
        for flag in r.get("warning_flags", []):
            warning_flag_counts[flag] = warning_flag_counts.get(flag, 0) + 1

    top_candidates = sorted(
        [r for r in results if r.get("classification") in ["採用候補", "条件付き候補"]],
        key=lambda x: x.get("total_score", 0), reverse=True
    )[:10]

    try:
        usd_jpy = get_usd_jpy()
    except Exception:
        usd_jpy = 155.0

    job = latest_job()

    return clean_for_json({
        "screening_status": p.get("status", "idle"),
        "screening_running": p.get("running", False),
        "started_at": p.get("started_at"),
        "finished_at": p.get("finished_at"),
        "total_universe": all_count,
        "total_results": len(results),
        "total_exclusions": len(exclusions),
        "price_pass": len([r for r in results if r.get("jpy_price", 9999) <= 3000]),
        "adopted_count": classification_counts.get("採用候補", 0),
        "conditional_count": classification_counts.get("条件付き候補", 0),
        "watch_count": classification_counts.get("監視候補", 0),
        "low_score_count": classification_counts.get("低スコア", 0),
        "classification_counts": classification_counts,
        "vol_cycle_counts": vol_cycle_counts,
        "chart_cycle_counts": chart_cycle_counts,
        "warning_flag_counts": warning_flag_counts,
        "top_candidates": top_candidates,
        "usd_jpy": usd_jpy,
        "sample_mode": is_sample_mode(),
        "latest_job": job,
    })


@router.get("/universe")
def get_universe_info():
    from app.services.universe import get_universe
    universe = get_universe(["JP", "US"], include_adr=True, use_real=False)
    return {
        "total": len(universe),
        "jp_count": len([s for s in universe if s.get("market") == "JP"]),
        "us_count": len([s for s in universe if s.get("market") == "US" and not s.get("is_adr")]),
        "adr_count": len([s for s in universe if s.get("is_adr")]),
        "sample": universe[:5],
    }
