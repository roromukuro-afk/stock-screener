"""自動化パイプライン API — CRON_SECRET で保護"""
import os
import threading
from typing import Optional
from fastapi import APIRouter, HTTPException, Header, Request
from pydantic import BaseModel

from app.services import automation
from app.utils import clean_for_json

router = APIRouter(prefix="/api/automation", tags=["automation"])


def _check_secret(x_cron_secret: Optional[str], authorization: Optional[str], allow_local: bool = False):
    """CRON_SECRETヘッダー認証 (GET status等は除く)"""
    required = os.getenv("CRON_SECRET", "")
    if not required:
        # 未設定の場合は localhost からだけ許可
        if not allow_local:
            raise HTTPException(503, "CRON_SECRET not configured")
        return
    provided = x_cron_secret or ""
    if not provided and authorization:
        if authorization.lower().startswith("bearer "):
            provided = authorization[7:]
    if provided != required:
        raise HTTPException(403, "invalid CRON_SECRET")


# ===== ステータス (open) =====
@router.get("/status")
def status():
    return clean_for_json(automation.get_automation_status())


@router.get("/jobs")
def jobs(limit: int = 50):
    return clean_for_json({"items": automation.list_jobs(limit)})


@router.get("/errors")
def errors(limit: int = 50):
    return clean_for_json({"items": automation.list_errors(limit)})


# ===== 実行 (要 CRON_SECRET) =====
class TriggerRequest(BaseModel):
    market: Optional[str] = "JP"
    trigger_type: Optional[str] = "manual"
    max_symbols: Optional[int] = 200
    min_score: Optional[float] = 65


def _run_async(target, *args, **kwargs):
    """非同期実行ラッパー (Render Free対策で長時間処理を避けつつ progress 確認可能に)"""
    t = threading.Thread(target=target, args=args, kwargs=kwargs, daemon=True)
    t.start()


@router.post("/run-daily-jp")
def run_daily_jp(req: TriggerRequest,
                 x_cron_secret: Optional[str] = Header(None),
                 authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_daily_market, "JP", req.trigger_type or "cron",
               req.max_symbols or 200)
    return {"status": "started", "job_type": "run-daily-jp"}


@router.post("/run-daily-us")
def run_daily_us(req: TriggerRequest,
                 x_cron_secret: Optional[str] = Header(None),
                 authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_daily_market, "US", req.trigger_type or "cron",
               req.max_symbols or 200)
    return {"status": "started", "job_type": "run-daily-us"}


@router.post("/run-screening-and-save-predictions")
def run_screening_save(req: TriggerRequest,
                       x_cron_secret: Optional[str] = Header(None),
                       authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_screening_and_save_predictions,
               req.market or "JP", req.trigger_type or "cron",
               req.max_symbols or 200, req.min_score or 65)
    return {"status": "started", "job_type": "screening-save"}


@router.post("/update-prediction-outcomes")
def update_outcomes(req: TriggerRequest,
                    x_cron_secret: Optional[str] = Header(None),
                    authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    return automation.update_prediction_outcomes(req.trigger_type or "cron")


@router.post("/review-predictions")
def review_predictions(req: TriggerRequest,
                       x_cron_secret: Optional[str] = Header(None),
                       authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    return automation.review_predictions(req.trigger_type or "cron")


@router.post("/save-reviews-as-training")
def save_reviews(req: TriggerRequest,
                 x_cron_secret: Optional[str] = Header(None),
                 authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    return automation.save_reviews_as_training(req.trigger_type or "cron")


@router.post("/run-training-builder-known-seed")
def run_seed(req: TriggerRequest,
             x_cron_secret: Optional[str] = Header(None),
             authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_training_builder_known_seed, req.trigger_type or "cron")
    return {"status": "started", "job_type": "training-known-seed"}


@router.post("/run-training-builder-smallcap")
def run_smallcap(req: TriggerRequest,
                 x_cron_secret: Optional[str] = Header(None),
                 authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_training_builder_smallcap, req.trigger_type or "cron")
    return {"status": "started", "job_type": "training-smallcap"}


@router.post("/run-full-daily-pipeline")
def run_full_pipeline(req: TriggerRequest,
                      x_cron_secret: Optional[str] = Header(None),
                      authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_full_daily_pipeline,
               req.market or "JP", req.trigger_type or "cron")
    return {"status": "started", "job_type": "full-daily-pipeline"}
