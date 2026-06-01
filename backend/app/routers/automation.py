"""自動化パイプライン API — CRON_SECRET で保護"""
import os
import threading
from typing import Optional
from datetime import date, timedelta as _td
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
    """自動化ステータス。DB schema不整合等でも500にせず degraded を返す。"""
    try:
        return clean_for_json(automation.get_automation_status())
    except Exception as e:
        return {"status": "degraded", "error": _safe_err(e),
                "hint": "schema migration が必要かもしれません: POST /api/automation/ensure-schema"}


@router.get("/jobs")
def jobs(limit: int = 50):
    try:
        return clean_for_json({"items": automation.list_jobs(limit)})
    except Exception as e:
        return {"status": "degraded", "items": [], "error": _safe_err(e)}


@router.get("/errors")
def errors(limit: int = 50):
    try:
        return clean_for_json({"items": automation.list_errors(limit)})
    except Exception as e:
        return {"status": "degraded", "items": [], "error": _safe_err(e)}


def _safe_err(e: Exception) -> str:
    """例外メッセージを1行・短めに (秘密情報を含めない)。"""
    s = str(e).strip().splitlines()
    return (s[0] if s else type(e).__name__)[:300]


# ===== schema migration (要 CRON_SECRET) =====
@router.post("/ensure-schema")
def ensure_schema_endpoint(x_cron_secret: Optional[str] = Header(None),
                           authorization: Optional[str] = Header(None)):
    """本番DBにモデル定義の不足テーブル/カラムを非破壊で追加する。
    ADD COLUMN IF NOT EXISTS / CREATE TABLE IF NOT EXISTS のみ (DROP/TRUNCATE禁止)。"""
    _check_secret(x_cron_secret, authorization)
    try:
        from app.database import ensure_schema
        result = ensure_schema()
        ok = len(result.get("errors", [])) == 0
        return {"status": "ok" if ok else "partial", **result}
    except Exception as e:
        return {"status": "failed", "error": _safe_err(e)}


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


@router.post("/compute-material-outcomes")
def compute_material_outcomes_endpoint(x_cron_secret: Optional[str] = Header(None),
                                       authorization: Optional[str] = Header(None)):
    """直近60日の MaterialEvent の outcome (T+1/3/5/10/20 と hit_20 等) を一括計算。
    historical_ohlcv キャッシュから読むため Render-safe (live fetch 無し)。
    """
    _check_secret(x_cron_secret, authorization)
    try:
        from app.services import material_outcome
        r = material_outcome.compute_material_outcomes(lookback_days=60, max_events=500)
        return clean_for_json(r)
    except Exception as e:
        return _degraded_schema_response(e)


@router.get("/material-category-performance")
def material_category_performance(min_samples: int = 3):
    """カテゴリ × ソース別の hit_20 率・平均 max_gain・サンプル数。
    どの種類の材料が本当に株価を動かすか empirical に検証する。"""
    try:
        from app.services import material_outcome
        return clean_for_json(material_outcome.get_category_performance(min_samples=min_samples))
    except Exception as e:
        return {"status": "degraded", "items": [], "error": _safe_err(e)}


@router.get("/material-source-effectiveness")
def material_source_effectiveness(min_samples: int = 5):
    """source_type 単体の予測力。どのニュース源を信用するべきか。"""
    try:
        from app.services import material_outcome
        return clean_for_json(material_outcome.get_source_effectiveness(min_samples=min_samples))
    except Exception as e:
        return {"status": "degraded", "items": [], "error": _safe_err(e)}


@router.post("/collect-macro-indicators")
def collect_macro_indicators_endpoint(x_cron_secret: Optional[str] = Header(None),
                                      authorization: Optional[str] = Header(None)):
    """USD/JPY, Nikkei225, TOPIX, VIX, 10yr, SOX, S&P500 等を Yahoo から日次取得"""
    _check_secret(x_cron_secret, authorization)
    try:
        from app.services import macro_collector
        return clean_for_json(macro_collector.collect_macro_indicators(period="3mo"))
    except Exception as e:
        return _degraded_schema_response(e)


@router.get("/ai-intelligence-summary")
def ai_intelligence_summary():
    """AI が今動作中の状態 (regime / 学習データ / 経験的有効性 / 最近の予測) を1コールで返す。
    /screener/learning-center 等の Web表示やデバッグ・運用監視用。"""
    out = {}
    # 1) マクロ regime
    try:
        from app.services import macro_collector
        out["macro"] = macro_collector.get_latest_snapshot()
    except Exception as e:
        out["macro"] = {"error": _safe_err(e)}
    # 2) 経験的 catalyst 有効性 (カテゴリ別)
    try:
        from app.services import material_outcome as _mo
        out["catalyst_category_performance"] = _mo.get_category_performance(min_samples=3)
        out["source_effectiveness"] = _mo.get_source_effectiveness(min_samples=3)
    except Exception as e:
        out["catalyst_category_performance"] = {"items": [], "error": _safe_err(e)}
        out["source_effectiveness"] = {"items": [], "error": _safe_err(e)}
    # 3) 材料件数サマリ
    try:
        from app.database import SessionLocal
        from app.models.models import MaterialEvent, MaterialOutcome, MacroIndicator
        from sqlalchemy import func as _f
        db = SessionLocal()
        try:
            out["material_event_count"] = db.query(MaterialEvent).count()
            out["material_outcome_count"] = (db.query(MaterialOutcome)
                                             .filter(MaterialOutcome.insufficient_data == False).count())
            out["macro_indicator_count"] = db.query(MacroIndicator).count()
        finally:
            db.close()
    except Exception as e:
        out["material_event_count"] = None
        out["material_outcome_count"] = None
    # 4) surge-20 学習データ + 直近予測
    try:
        from app.services import surge_20
        out["light_status"] = surge_20.get_light_status()
    except Exception as e:
        out["light_status"] = {"error": _safe_err(e)}
    return clean_for_json(out)


@router.get("/macro-snapshot")
def macro_snapshot():
    """マクロ指標の最新値 + リスクオン/オフ判定 (公開)"""
    try:
        from app.services import macro_collector
        return clean_for_json(macro_collector.get_latest_snapshot())
    except Exception as e:
        return {"status": "degraded", "indicators": {}, "error": _safe_err(e)}


@router.get("/materials-summary")
def materials_summary(limit_recent: int = 10):
    """material_events のソース別件数 + 最近のサンプル (EDINET / TDnet / RSS 等の効果を可視化)"""
    from app.database import SessionLocal
    from app.models.models import MaterialEvent
    from sqlalchemy import func as _f
    db = SessionLocal()
    try:
        total = db.query(MaterialEvent).count()
        by_type = dict(db.query(MaterialEvent.source_type, _f.count())
                       .group_by(MaterialEvent.source_type).all())
        by_rank = dict(db.query(MaterialEvent.source_rank, _f.count())
                       .group_by(MaterialEvent.source_rank).all())
        by_category = dict(db.query(MaterialEvent.catalyst_category, _f.count())
                           .group_by(MaterialEvent.catalyst_category).all())
        cutoff = (date.today() - _td(days=30)).isoformat()
        high_quality_recent = (db.query(MaterialEvent)
                               .filter(MaterialEvent.detected_at >= cutoff)
                               .filter(MaterialEvent.catalyst_quality_score >= 70)
                               .order_by(MaterialEvent.detected_at.desc())
                               .limit(limit_recent).all())
        items = [{
            "id": r.id, "symbol": r.symbol, "market": r.market,
            "title": (r.title or "")[:120],
            "source_type": r.source_type, "source_rank": r.source_rank,
            "catalyst_category": r.catalyst_category,
            "catalyst_quality_score": r.catalyst_quality_score,
            "published_at": r.published_at,
        } for r in high_quality_recent]
        return clean_for_json({
            "total": total, "by_source_type": by_type,
            "by_source_rank": by_rank, "by_catalyst_category": by_category,
            "high_quality_recent": items,
        })
    finally:
        db.close()


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
    from app.services import surge_20 as s20
    if s20.is_heavy_running():
        return {"status": "busy", "running_task": s20.heavy_status().get("task")}
    _run_async(automation.run_surge_20_auto_orchestrator,
               req.market or "JP", req.trigger_type or "cron", "all")
    return {"status": "started", "job_type": "surge-20-auto-orchestrator"}


@router.post("/auto-save-surge-20-predictions")
def auto_save_surge_20_predictions(req: TriggerRequest,
                                    x_cron_secret: Optional[str] = Header(None),
                                    authorization: Optional[str] = Header(None)):
    """軽量auto-save (lock付き)。schema不整合等でも500にせず degraded を返す。"""
    _check_secret(x_cron_secret, authorization)
    lock_key = "surge20_auto_save_lock"
    try:
        if not automation.acquire_db_lock(lock_key, owner=f"auto_save_{req.market}"):
            return {"status": "busy", "lock": lock_key}
    except Exception as e:
        return _degraded_schema_response(e)
    try:
        return clean_for_json(automation.auto_save_surge_20_predictions(
            req.market or "JP", req.trigger_type or "cron", 20, 70.0,
        ))
    except Exception as e:
        return _degraded_schema_response(e)
    finally:
        try:
            automation.release_db_lock(lock_key)
        except Exception:
            pass


def _degraded_schema_response(e: Exception) -> dict:
    """DB例外時の共通レスポンス。schema不足の可能性を案内 (500を返さない)。"""
    msg = _safe_err(e)
    schema_keywords = ("does not exist", "no such column", "no such table",
                       "undefinedcolumn", "undefined column", "relation",
                       "has no column")
    is_schema = any(k in msg.lower() for k in schema_keywords)
    out = {"status": "degraded", "error": msg}
    if is_schema:
        out["message"] = "schema migration required"
        out["hint"] = "POST /api/automation/ensure-schema を実行してください"
    return out


@router.post("/cleanup-stale-jobs")
def cleanup_stale_jobs(req: TriggerRequest,
                       x_cron_secret: Optional[str] = Header(None),
                       authorization: Optional[str] = Header(None)):
    _check_secret(x_cron_secret, authorization)
    return automation.cleanup_stale_jobs(running_minutes=30)


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
    """教師データ化。schema不整合等でも500にせず degraded を返す。"""
    _check_secret(x_cron_secret, authorization)
    try:
        return clean_for_json(automation.save_surge_20_reviews_as_training(req.trigger_type or "cron"))
    except Exception as e:
        return _degraded_schema_response(e)


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
