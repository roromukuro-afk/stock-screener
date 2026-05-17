"""ユニバース管理 API"""
import threading
from typing import Dict, List, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import pandas as pd
import io
from datetime import datetime

from app.services import universe_fetcher, universe_db
from app.services.price_fetcher import get_stock_quote_with_freshness, get_usd_jpy
from app.utils import clean_for_json

router = APIRouter(prefix="/api/universe", tags=["universe"])


# ===== サマリ =====
@router.get("/summary")
def universe_summary():
    s = universe_db.get_universe_summary()
    fresh = universe_db.get_freshness_summary()
    jobs = universe_db.latest_update_jobs(5)
    return clean_for_json({
        "universe": s,
        "freshness": fresh,
        "latest_jobs": jobs,
    })


# ===== 更新ジョブ実行 =====
_update_progress: Dict = {"running": False, "status": "idle", "message": "", "source": None}
_update_lock = threading.Lock()


def _set_progress(status: str, message: str = "", source: str = None, running: bool = None):
    with _update_lock:
        _update_progress["status"] = status
        _update_progress["message"] = message
        if source is not None:
            _update_progress["source"] = source
        if running is not None:
            _update_progress["running"] = running


def _update_jpx_sync():
    _set_progress("fetching JPX", "Downloading from jpx.co.jp...", source="jpx", running=True)
    job_id = universe_db.create_update_job("jpx")
    items, meta = universe_fetcher.fetch_jpx()
    meta["source"] = "jpx"
    universe_db.save_universe_source_file(meta)
    if meta.get("status") != "ok":
        universe_db.complete_update_job(job_id, {}, status="failed", error=meta.get("error"))
        _set_progress("failed", meta.get("error", "JPX fetch failed"), running=False)
        return
    result = universe_db.upsert_universe_items(items, "jpx")
    summary = {
        "total_raw_count": len(items),
        "normalized_count": len(items),
        "eligible_count": sum(1 for x in items if x.get("is_screening_eligible")),
        "excluded_count": sum(1 for x in items if not x.get("is_screening_eligible")),
    }
    universe_db.complete_update_job(job_id, summary, status="completed")
    _set_progress("completed", f"JPX: {len(items)} symbols loaded ({summary['eligible_count']} eligible)", running=False)


def _update_nasdaq_sync():
    _set_progress("fetching nasdaqlisted", "Downloading from nasdaqtrader.com...", source="nasdaqlisted", running=True)
    job_id = universe_db.create_update_job("nasdaqlisted")
    items, meta = universe_fetcher.fetch_nasdaq_listed()
    meta["source"] = "nasdaqlisted"
    universe_db.save_universe_source_file(meta)
    if meta.get("status") != "ok":
        universe_db.complete_update_job(job_id, {}, status="failed", error=meta.get("error"))
        _set_progress("failed", meta.get("error"), running=False)
        return
    universe_db.upsert_universe_items(items, "nasdaqlisted")
    summary = {
        "total_raw_count": len(items),
        "normalized_count": len(items),
        "eligible_count": sum(1 for x in items if x.get("is_screening_eligible")),
        "excluded_count": sum(1 for x in items if not x.get("is_screening_eligible")),
    }
    universe_db.complete_update_job(job_id, summary, status="completed")
    _set_progress("completed", f"nasdaqlisted: {len(items)} loaded", running=False)


def _update_other_listed_sync():
    _set_progress("fetching otherlisted", "Downloading from nasdaqtrader.com...", source="otherlisted", running=True)
    job_id = universe_db.create_update_job("otherlisted")
    items, meta = universe_fetcher.fetch_other_listed()
    meta["source"] = "otherlisted"
    universe_db.save_universe_source_file(meta)
    if meta.get("status") != "ok":
        universe_db.complete_update_job(job_id, {}, status="failed", error=meta.get("error"))
        _set_progress("failed", meta.get("error"), running=False)
        return
    universe_db.upsert_universe_items(items, "otherlisted")
    summary = {
        "total_raw_count": len(items),
        "normalized_count": len(items),
        "eligible_count": sum(1 for x in items if x.get("is_screening_eligible")),
        "excluded_count": sum(1 for x in items if not x.get("is_screening_eligible")),
    }
    universe_db.complete_update_job(job_id, summary, status="completed")
    _set_progress("completed", f"otherlisted: {len(items)} loaded", running=False)


def _update_all_sync():
    """JPX + Nasdaq listed + Other listed を全部更新"""
    _set_progress("running", "Fetching all sources...", source="all", running=True)
    try:
        _update_jpx_sync()
        _update_nasdaq_sync()
        _update_other_listed_sync()
        _set_progress("completed", "All sources updated", source="all", running=False)
    except Exception as e:
        _set_progress("failed", str(e), running=False)


@router.post("/update")
def update_all():
    if _update_progress.get("running"):
        raise HTTPException(409, "ユニバース更新がすでに実行中です")
    t = threading.Thread(target=_update_all_sync, daemon=True)
    t.start()
    return {"status": "started", "message": "ユニバース更新を開始しました"}


@router.post("/update/jpx")
def update_jpx():
    if _update_progress.get("running"):
        raise HTTPException(409, "更新実行中")
    t = threading.Thread(target=_update_jpx_sync, daemon=True)
    t.start()
    return {"status": "started", "message": "JPX更新を開始しました"}


@router.post("/update/nasdaq")
def update_nasdaq():
    if _update_progress.get("running"):
        raise HTTPException(409, "更新実行中")
    t = threading.Thread(target=_update_nasdaq_sync, daemon=True)
    t.start()
    return {"status": "started", "message": "NASDAQ listed更新を開始しました"}


@router.post("/update/other-listed")
def update_other_listed():
    if _update_progress.get("running"):
        raise HTTPException(409, "更新実行中")
    t = threading.Thread(target=_update_other_listed_sync, daemon=True)
    t.start()
    return {"status": "started", "message": "Other listed更新を開始しました"}


@router.post("/update/adr")
def update_adr():
    # nasdaqlisted + otherlistedのADR分のみを再分類
    return {"status": "info", "message": "ADRは nasdaqlisted/otherlisted 取得時に自動分類されます。update_allを実行してください。"}


@router.get("/update/progress")
def update_progress():
    with _update_lock:
        return dict(_update_progress)


# ===== リスト =====
@router.get("/list")
def list_all(eligible_only: bool = False, market: str = None, limit: int = 1000, offset: int = 0):
    return universe_db.list_universe(eligible_only=eligible_only, market=market, limit=limit, offset=offset)


@router.get("/eligible")
def list_eligible(market: str = None, limit: int = 1000, offset: int = 0):
    return universe_db.list_universe(eligible_only=True, market=market, limit=limit, offset=offset)


@router.get("/excluded")
def list_excluded(market: str = None, limit: int = 1000, offset: int = 0):
    from app.database import SessionLocal
    from app.models.models import UniverseSymbol
    db = SessionLocal()
    try:
        q = db.query(UniverseSymbol).filter(UniverseSymbol.is_screening_eligible == False)
        if market:
            q = q.filter(UniverseSymbol.market == market)
        total = q.count()
        rows = q.order_by(UniverseSymbol.market, UniverseSymbol.symbol).limit(limit).offset(offset).all()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [universe_db._to_dict(r) for r in rows],
        }
    finally:
        db.close()


# ===== 価格鮮度 =====
class RefreshRequest(BaseModel):
    markets: Optional[List[str]] = None
    include_adr: bool = True
    chunk_size: int = 50
    max_symbols: int = 200


_refresh_progress: Dict = {"running": False, "processed": 0, "total": 0, "fresh": 0, "stale": 0, "failed": 0, "status": "idle"}


def _refresh_prices_sync(req: RefreshRequest):
    syms = universe_db.list_eligible_yahoo_symbols(
        markets=req.markets, max_count=req.max_symbols, include_adr=req.include_adr
    )
    fx = get_usd_jpy()
    with _update_lock:
        _refresh_progress.update({"running": True, "processed": 0, "total": len(syms), "fresh": 0, "stale": 0, "failed": 0, "status": "running"})

    for s in syms:
        sym = s["yahoo_symbol"]
        market = s.get("market", "US")
        try:
            quote = get_stock_quote_with_freshness(sym, market=market)
            if quote.get("price") is None:
                with _update_lock:
                    _refresh_progress["failed"] += 1
            else:
                # 円換算価格
                price = quote["price"]
                jpy_price = price if market == "JP" else price * fx
                quote["jpy_price"] = jpy_price
                quote["currency"] = "JPY" if market == "JP" else "USD"
                universe_db.save_price_freshness(sym, market, quote)
                with _update_lock:
                    if quote.get("is_stale"):
                        _refresh_progress["stale"] += 1
                    else:
                        _refresh_progress["fresh"] += 1
        except Exception:
            with _update_lock:
                _refresh_progress["failed"] += 1
        with _update_lock:
            _refresh_progress["processed"] += 1

    with _update_lock:
        _refresh_progress.update({"running": False, "status": "completed"})


@router.post("/refresh-prices")
def refresh_prices(req: RefreshRequest):
    if _refresh_progress.get("running"):
        raise HTTPException(409, "価格更新がすでに実行中です")
    t = threading.Thread(target=_refresh_prices_sync, args=(req,), daemon=True)
    t.start()
    return {"status": "started", "message": f"価格鮮度チェックを最大{req.max_symbols}件で開始しました"}


@router.get("/refresh-progress")
def refresh_progress():
    with _update_lock:
        return dict(_refresh_progress)


@router.get("/stale-prices")
def stale_prices(limit: int = 500):
    return clean_for_json({"items": universe_db.list_stale_prices(limit=limit)})


# ===== Export =====
@router.get("/export/csv")
def export_csv(eligible_only: bool = False):
    data = universe_db.list_universe(eligible_only=eligible_only, limit=20000)
    df = pd.DataFrame(data["items"])
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    fname = f"universe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )


@router.get("/export/excel")
def export_excel():
    data = universe_db.list_universe(eligible_only=False, limit=20000)
    eligible = universe_db.list_universe(eligible_only=True, limit=20000)

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        if data["items"]:
            pd.DataFrame(data["items"]).to_excel(writer, sheet_name="All", index=False)
        if eligible["items"]:
            pd.DataFrame(eligible["items"]).to_excel(writer, sheet_name="Eligible", index=False)
    buf.seek(0)
    fname = f"universe_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=buf.read(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"}
    )
