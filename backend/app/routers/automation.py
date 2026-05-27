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


@router.post("/research-materials-daily")
def research_materials_daily(req: TriggerRequest,
                              x_cron_secret: Optional[str] = Header(None),
                              authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    from app.services import material_auto_collector
    _run_async(material_auto_collector.collect_all_materials_daily)
    return {"status": "started", "job_type": "research-materials-daily"}


@router.post("/research-materials-jp")
def research_materials_jp(req: TriggerRequest,
                          x_cron_secret: Optional[str] = Header(None),
                          authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    from app.services import material_auto_collector
    _run_async(material_auto_collector.collect_jp_materials)
    return {"status": "started", "job_type": "research-materials-jp"}


@router.post("/research-materials-us")
def research_materials_us(req: TriggerRequest,
                          x_cron_secret: Optional[str] = Header(None),
                          authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    from app.services import material_auto_collector
    _run_async(material_auto_collector.collect_us_materials, None, req.max_symbols or 30)
    return {"status": "started", "job_type": "research-materials-us"}


@router.post("/test-cron-secret")
def test_cron_secret(req: TriggerRequest,
                     x_cron_secret: Optional[str] = Header(None),
                     authorization: Optional[str] = Header(None)):
    """CRON_SECRET接続テスト用エンドポイント (Web UIから設定確認可能)

    レスポンスコード:
        200 = secret一致
        403 = secret不一致
        503 = Render ENVにCRON_SECRET未設定 (Render Dashboard で設定が必要)
    """
    required = os.getenv("CRON_SECRET", "")
    if not required:
        raise HTTPException(503, "Render ENV CRON_SECRET not configured. Set it in Render Dashboard → Environment.")
    provided = x_cron_secret or ""
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:]
    if provided != required:
        raise HTTPException(403, "invalid CRON_SECRET (Render ENVとheaderの値が不一致)")
    return {
        "status": "ok",
        "message": "CRON_SECRETが一致しました",
        "cron_secret_env_configured": True,
        "cron_secret_effective_configured": True,
    }


@router.get("/next-runs")
def next_runs():
    """次回 cron 予定 (GitHub Actions cron 設定からの推測)"""
    from datetime import datetime, timezone, timedelta
    now = datetime.now(timezone.utc)
    # 予定リスト (UTC -> JST)
    schedules = [
        {"job": "JP daily", "cron_utc": "40 7 * * 1-5", "jst": "16:40 平日"},
        {"job": "JP screening", "cron_utc": "10 8 * * 1-5", "jst": "17:10 平日"},
        {"job": "US daily", "cron_utc": "40 22 * * 1-5", "jst": "07:40 平日"},
        {"job": "US screening", "cron_utc": "10 23 * * 1-5", "jst": "08:10 平日"},
        {"job": "outcomes + review + training save", "cron_utc": "0 0 * * 1-5", "jst": "09:00 平日"},
        {"job": "weekend training builder", "cron_utc": "0 14 * * 0,6", "jst": "23:00 土日"},
    ]
    return {"now_utc": now.isoformat(), "schedules": schedules}


@router.post("/run-surge-20-daily")
def run_surge_20_daily(req: TriggerRequest,
                       x_cron_secret: Optional[str] = Header(None),
                       authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_surge_20_daily,
               req.market or "JP", req.trigger_type or "cron",
               req.max_symbols or 100)
    return {"status": "started", "job_type": "surge-20-daily"}


@router.post("/run-one-day-surge-detection")
def run_one_day_surge_detection(req: TriggerRequest,
                                x_cron_secret: Optional[str] = Header(None),
                                authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_one_day_surge_detection,
               req.market or "JP", req.trigger_type or "cron",
               req.max_symbols or 150)
    return {"status": "started", "job_type": "one-day-surge-detection"}


@router.post("/run-surge-20-auto-orchestrator")
def run_surge_20_auto_orchestrator(req: TriggerRequest,
                                    x_cron_secret: Optional[str] = Header(None),
                                    authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_surge_20_auto_orchestrator,
               req.market or "JP", req.trigger_type or "cron", "all")
    return {"status": "started", "job_type": "surge-20-auto-orchestrator"}


@router.post("/auto-save-surge-20-predictions")
def auto_save_surge_20_predictions(req: TriggerRequest,
                                    x_cron_secret: Optional[str] = Header(None),
                                    authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    return automation.auto_save_surge_20_predictions(
        req.market or "JP", req.trigger_type or "cron",
        20, 70.0,
    )


@router.post("/review-surge-20-predictions")
def review_surge_20_predictions(req: TriggerRequest,
                                 x_cron_secret: Optional[str] = Header(None),
                                 authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.review_surge_20_predictions, req.trigger_type or "cron")
    return {"status": "started", "job_type": "review-surge-20-predictions"}


@router.post("/save-surge-20-reviews-as-training")
def save_surge_20_reviews_as_training(req: TriggerRequest,
                                       x_cron_secret: Optional[str] = Header(None),
                                       authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    return automation.save_surge_20_reviews_as_training(req.trigger_type or "cron")


@router.post("/run-surge-20-expand-training")
def run_surge_20_expand_training(req: TriggerRequest,
                                  x_cron_secret: Optional[str] = Header(None),
                                  authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    # TriggerRequestに priority_mode などはないので、デフォルト known_surge_first
    _run_async(automation.run_surge_20_expand_training,
               req.market or "JP", req.trigger_type or "cron",
               req.max_symbols or 300, 30, 0, "known_surge_first")
    return {"status": "started", "job_type": "surge-20-expand-training"}


@router.post("/run-surge-20-candidate-build")
def run_surge_20_candidate_build(req: TriggerRequest,
                                  x_cron_secret: Optional[str] = Header(None),
                                  authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_surge_20_candidate_build,
               req.market or "JP", req.trigger_type or "cron",
               req.max_symbols or 200)
    return {"status": "started", "job_type": "surge-20-candidate-build"}


@router.post("/run-surge-ranking-generation")
def run_surge_ranking_generation(req: TriggerRequest,
                                  x_cron_secret: Optional[str] = Header(None),
                                  authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    from app.services import surge_20
    _run_async(surge_20.generate_all_rankings, req.market or "JP", None, 100)
    return {"status": "started", "job_type": "surge-ranking-generation"}


@router.post("/run-full-daily-pipeline")
def run_full_pipeline(req: TriggerRequest,
                      x_cron_secret: Optional[str] = Header(None),
                      authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    _run_async(automation.run_full_daily_pipeline,
               req.market or "JP", req.trigger_type or "cron")
    return {"status": "started", "job_type": "full-daily-pipeline"}
