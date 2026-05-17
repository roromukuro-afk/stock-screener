from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.services.screener import run_screening_background, get_progress
from app.utils import clean_for_json

router = APIRouter(prefix="/api/screening", tags=["screening"])


class ScreeningParams(BaseModel):
    markets: List[str] = ["JP", "US"]
    include_adr: bool = False
    use_real_data: bool = True
    price_limit: float = 3000
    min_vol_jp: float = 30000
    min_vol_us: float = 100000
    min_score: float = 0
    excluded_symbols: List[str] = []
    max_symbols: int = 0           # 0 = 制限なし。Render Free対策で本番では小さく
    use_db_universe: bool = True   # DBの普通株+ADRのみ対象
    enforce_freshness_gate: bool = True  # 古い価格データを除外


@router.post("/run")
def run_screening(params: ScreeningParams):
    progress = get_progress()
    if progress.get("running"):
        raise HTTPException(status_code=409, detail="スクリーニングが既に実行中です")
    run_screening_background(params.model_dump())
    return {"message": "スクリーニングを開始しました", "status": "started"}


@router.get("/progress")
def screening_progress():
    p = get_progress()
    return {
        "running": p["running"],
        "status": p["status"],
        "total": p["total"],
        "processed": p["processed"],
        "failed": p["failed"],
        "result_count": len(p.get("results", [])),
        "exclusion_count": len(p.get("exclusions", [])),
        "started_at": p.get("started_at"),
        "finished_at": p.get("finished_at"),
        "error": p.get("error"),
    }


@router.get("/results")
def get_results(
    classification: Optional[str] = None,
    market: Optional[str] = None,
    min_score: float = 0,
    limit: int = 500,
    offset: int = 0
):
    p = get_progress()
    results = p.get("results", [])

    if classification:
        results = [r for r in results if r.get("classification") == classification]
    if market:
        results = [r for r in results if r.get("market") == market]
    if min_score > 0:
        results = [r for r in results if r.get("total_score", 0) >= min_score]

    total = len(results)
    results = results[offset:offset + limit]

    return clean_for_json({
        "total": total,
        "offset": offset,
        "limit": limit,
        "results": results,
    })


@router.get("/exclusions")
def get_exclusions(limit: int = 500, offset: int = 0):
    p = get_progress()
    exclusions = p.get("exclusions", [])
    total = len(exclusions)
    return clean_for_json({
        "total": total,
        "exclusions": exclusions[offset:offset + limit],
    })
