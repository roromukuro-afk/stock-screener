"""予測ログ・検証・教師化 / 材料調査 / チャート予測 / エントリー / 自動収集 API"""
from typing import List, Dict, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
import pandas as pd
import io
from datetime import datetime

from app.services import (
    prediction_log as plog,
    auto_training,
    material_research,
)
from app.services.entry_planner import build_entry_plan, build_chart_forecast
from app.utils import clean_for_json


router = APIRouter(prefix="/api", tags=["prediction"])


# ===========================================
# 予測ログ
# ===========================================
class SaveLogRequest(BaseModel):
    result: Dict
    entry_plan: Optional[Dict] = None


@router.post("/prediction-log/save")
def save_log(req: SaveLogRequest):
    result = req.result or {}
    ep = req.entry_plan or build_entry_plan(result)
    log_id = plog.save_prediction_log(result, ep)
    return {"status": "ok", "log_id": log_id}


@router.get("/prediction-log/list")
def list_logs(limit: int = 200, status: Optional[str] = None):
    return clean_for_json(plog.list_prediction_logs(limit=limit, status=status))


@router.get("/prediction-log/{log_id}")
def get_log(log_id: int):
    d = plog.get_prediction_log(log_id)
    if not d:
        raise HTTPException(404, "Not found")
    return clean_for_json(d)


@router.delete("/prediction-log/{log_id}")
def delete_log(log_id: int):
    ok = plog.delete_prediction_log(log_id)
    if not ok:
        raise HTTPException(404, "Not found")
    return {"deleted": True}


# ===========================================
# 予測検証
# ===========================================
@router.post("/prediction-review/update-outcomes")
def update_all_outcomes(limit: int = 100):
    return plog.update_all_outcomes(limit=limit)


@router.post("/prediction-review/review/{log_id}")
def review_one(log_id: int):
    return clean_for_json(plog.review_prediction(log_id))


@router.post("/prediction-review/review-all")
def review_all():
    return plog.review_all()


@router.get("/prediction-review/summary")
def summary():
    return clean_for_json(plog.review_summary())


@router.get("/prediction-review/results")
def results(limit: int = 200):
    return clean_for_json(plog.list_reviews(limit=limit))


@router.post("/prediction-review/save-as-training/{log_id}")
def save_as_training(log_id: int):
    return plog.save_review_as_training(log_id)


@router.post("/prediction-review/save-all-reviewed-as-training")
def save_all_reviewed_as_training():
    return plog.save_all_reviewed_as_training()


@router.get("/prediction-review/export/csv")
def export_csv():
    data = plog.list_reviews(limit=10000)
    rows = []
    for it in data["items"]:
        d = {k: v for k, v in it.items() if not isinstance(v, (dict, list))}
        if it.get("review"):
            for k, v in it["review"].items():
                d[f"review_{k}"] = v
        rows.append(d)
    df = pd.DataFrame(rows)
    buf = io.StringIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename=prediction_reviews_{datetime.now():%Y%m%d_%H%M%S}.csv"}
    )


# ===========================================
# Entry plan
# ===========================================
class EntryPlanRequest(BaseModel):
    result: Dict


@router.post("/entry-plan/generate")
def entry_plan_generate(req: EntryPlanRequest):
    return clean_for_json(build_entry_plan(req.result))


@router.post("/chart-forecast/generate")
def chart_forecast_generate(req: EntryPlanRequest):
    ep = build_entry_plan(req.result)
    fc = build_chart_forecast(req.result, ep)
    return clean_for_json({"entry_plan": ep, "forecast": fc})


# ===========================================
# AI 材料調査
# ===========================================
class MaterialReq(BaseModel):
    symbol: str
    market: str = "JP"
    user_text: Optional[str] = None
    urls: Optional[List[str]] = None
    save: bool = True


@router.post("/materials/research")
def material_research_api(req: MaterialReq):
    result = material_research.research_material(
        symbol=req.symbol, market=req.market,
        user_text=req.user_text, urls=req.urls,
    )
    if req.save:
        # MaterialEvent に保存
        from app.database import SessionLocal
        from app.models.models import MaterialEvent
        db = SessionLocal()
        try:
            ev = MaterialEvent(
                symbol=req.symbol,
                yahoo_symbol=req.symbol,
                market=req.market,
                title=result.get("title") or f"{req.symbol} material research",
                summary=result.get("summary"),
                source_url=result.get("material_source_url"),
                source_type=result.get("material_source_type"),
                source_rank=result.get("material_source_rank"),
                catalyst_category=result.get("catalyst_category"),
                catalyst_timing=result.get("material_timing"),
                catalyst_quality_score=result.get("catalyst_quality_score"),
                catalyst_continuity_score=result.get("catalyst_continuity_score"),
                catalyst_freshness_score=result.get("catalyst_freshness_score"),
                catalyst_surprise_score=result.get("catalyst_surprise_score"),
                theme_tailwind_score=result.get("theme_tailwind_score"),
                material_confirmed=result.get("material_confirmed"),
                material_text=req.user_text,
                ai_analysis=result.get("ai_analysis"),
                risk_flags={
                    "bad_news_unresolved_flag": result.get("bad_news_unresolved_flag"),
                    "dilution_risk_flag": result.get("dilution_risk_flag"),
                    "going_concern_risk_flag": result.get("going_concern_risk_flag"),
                    "delisting_risk_flag": result.get("delisting_risk_flag"),
                    "material_exhaustion_risk_score": result.get("material_exhaustion_risk_score"),
                },
            )
            db.add(ev)
            db.commit()
            result["material_event_id"] = ev.id
        finally:
            db.close()
    return clean_for_json(result)


@router.get("/materials/{symbol}")
def get_materials(symbol: str, limit: int = 20):
    from app.database import SessionLocal
    from app.models.models import MaterialEvent
    db = SessionLocal()
    try:
        rows = (db.query(MaterialEvent)
                .filter(MaterialEvent.symbol == symbol)
                .order_by(MaterialEvent.id.desc()).limit(limit).all())
        return clean_for_json({"total": len(rows), "items": [
            {
                "id": r.id, "symbol": r.symbol, "title": r.title,
                "summary": r.summary, "source_url": r.source_url,
                "source_type": r.source_type, "source_rank": r.source_rank,
                "catalyst_category": r.catalyst_category,
                "catalyst_quality_score": r.catalyst_quality_score,
                "catalyst_continuity_score": r.catalyst_continuity_score,
                "catalyst_freshness_score": r.catalyst_freshness_score,
                "catalyst_surprise_score": r.catalyst_surprise_score,
                "material_confirmed": r.material_confirmed,
                "risk_flags": r.risk_flags,
                "detected_at": r.detected_at.isoformat() if r.detected_at else None,
            } for r in rows
        ]})
    finally:
        db.close()


@router.get("/materials/recent")
def materials_recent(limit: int = 100):
    from app.database import SessionLocal
    from app.models.models import MaterialEvent
    db = SessionLocal()
    try:
        rows = db.query(MaterialEvent).order_by(MaterialEvent.id.desc()).limit(limit).all()
        return clean_for_json({"total": len(rows), "items": [
            {"id": r.id, "symbol": r.symbol, "title": r.title,
             "catalyst_category": r.catalyst_category,
             "catalyst_quality_score": r.catalyst_quality_score,
             "material_confirmed": r.material_confirmed,
             "detected_at": r.detected_at.isoformat() if r.detected_at else None}
            for r in rows
        ]})
    finally:
        db.close()


# ===========================================
# 自動教師データ収集
# ===========================================
class AutoTrainReq(BaseModel):
    markets: List[str] = ["JP", "US"]
    target_date: Optional[str] = None
    threshold_percent: float = 20.0
    max_symbols: int = 500
    include_adr: bool = True


@router.post("/auto-training/run-daily")
def auto_training_run(req: AutoTrainReq):
    progress = auto_training.get_progress()
    if progress.get("running"):
        raise HTTPException(409, "auto-training already running")
    auto_training.run_in_background(req.model_dump())
    return {"status": "started", "message": "自動教師データ収集を開始しました"}


@router.get("/auto-training/progress")
def auto_training_progress():
    return clean_for_json(auto_training.get_progress())


@router.get("/auto-training/jobs")
def auto_training_jobs(limit: int = 30):
    return clean_for_json({"items": auto_training.list_jobs(limit=limit)})


@router.get("/auto-training/results")
def auto_training_results(job_id: Optional[int] = None, limit: int = 500):
    return clean_for_json(auto_training.list_results(job_id=job_id, limit=limit))
