"""過去5年教師データ構築 API"""
import io
import pandas as pd
from datetime import datetime, date, timedelta
from typing import List, Optional
from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import training_builder
from app.utils import clean_for_json

router = APIRouter(prefix="/api/training-builder", tags=["training-builder"])


class BuildAllRequest(BaseModel):
    markets: List[str] = ["JP"]
    include_adr: bool = True
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    max_symbols: int = 50
    chunk_size: int = 20
    surge_threshold_percent: float = 20.0
    semi_surge_threshold_percent: float = 15.0
    negative_sample_ratio: float = 3.0
    target_mode: str = "all"
    # all / low_price_only / small_cap_priority / high_volatility_priority
    # / jp_growth_priority / jp_low_price_priority / us_small_cap_priority
    # / us_low_price_priority / adr_priority / random_sample / known_surge_seed
    exclude_etf: bool = True
    exclude_warrant: bool = True
    exclude_unit: bool = True
    exclude_right: bool = True
    exclude_preferred: bool = True


@router.post("/build-all")
def build_all(req: BuildAllRequest):
    p = training_builder.get_progress()
    if p.get("running"):
        raise HTTPException(409, "training builder is already running")
    params = req.model_dump()
    if not params.get("end_date"):
        params["end_date"] = date.today().isoformat()
    if not params.get("start_date"):
        params["start_date"] = (date.today() - timedelta(days=365 * 5)).isoformat()
    training_builder.run_in_background(params)
    return {"status": "started",
            "message": f"過去5年教師データ構築を開始(対象 {req.max_symbols}銘柄)"}


@router.post("/fetch-historical")
def fetch_only(req: BuildAllRequest):
    # 同じ start ロジックでフェーズ "fetching" のみ走らせるラッパーは複雑になるため、
    # build-all と同じ実装。プロデュース時は max_symbols を小さく指定すること。
    return build_all(req)


@router.get("/progress")
def progress():
    return clean_for_json(training_builder.get_progress())


@router.get("/summary")
def summary():
    return clean_for_json(training_builder.get_summary())


@router.get("/quality-report")
def quality():
    return clean_for_json(training_builder.quality_report())


@router.get("/feature-stats")
def stats():
    return clean_for_json(training_builder.feature_stats())


@router.get("/export/csv")
def export_csv():
    from app.database import SessionLocal
    from app.models.models import TrainingFeatureVector
    db = SessionLocal()
    try:
        rows = db.query(TrainingFeatureVector).all()
        cols = ["id", "symbol", "market", "feature_asof_date", "case_type",
                "close", "price_change_5d", "price_change_20d",
                "volume_ratio_5d", "volume_ratio_20d",
                "ma25_deviation", "resistance_upside", "support_distance",
                "overextension_score", "chart_volume_score",
                "label_hit_20_percent", "label_max_gain_20d",
                "label_max_drawdown_20d", "label_success_class"]
        data = [{c: getattr(r, c) for c in cols} for r in rows]
        df = pd.DataFrame(data)
        buf = io.StringIO()
        df.to_csv(buf, index=False, encoding="utf-8-sig")
        return Response(
            content=buf.getvalue().encode("utf-8-sig"),
            media_type="text/csv; charset=utf-8-sig",
            headers={"Content-Disposition":
                     f"attachment; filename=training_features_{datetime.now():%Y%m%d_%H%M%S}.csv"}
        )
    finally:
        db.close()
