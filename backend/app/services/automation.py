"""自動化パイプライン: cron実行ステップ群"""
import os
import threading
import traceback
from datetime import datetime, date, timedelta
from typing import Dict, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models.models import (
    AutomationJob, AutomationError, AutomationLock, AutomationSetting,
    AARAnalysisCase, MaterialEvent, PredictionLog,
)
from app.services import (
    auto_training, training_builder, aar_db, prediction_log,
)


def _create_job(job_type: str, market: str, trigger_type: str = "cron") -> int:
    db: Session = SessionLocal()
    try:
        run_key = f"{date.today().isoformat()}-{job_type}-{market}"
        # 同日重複チェック
        existing = (db.query(AutomationJob)
                    .filter(AutomationJob.run_key == run_key)
                    .filter(AutomationJob.status == "running")
                    .first())
        if existing:
            return existing.id
        j = AutomationJob(
            job_type=job_type, market=market, status="running",
            trigger_type=trigger_type, run_key=run_key,
        )
        db.add(j); db.commit()
        return j.id
    finally:
        db.close()


def _finish_job(job_id: int, status: str = "completed", **counters):
    db: Session = SessionLocal()
    try:
        j = db.query(AutomationJob).filter(AutomationJob.id == job_id).first()
        if not j:
            return
        j.status = status
        j.finished_at = datetime.utcnow()
        if j.started_at and j.finished_at:
            j.duration_seconds = (j.finished_at - j.started_at).total_seconds()
        for k, v in counters.items():
            if hasattr(j, k):
                setattr(j, k, v)
        db.commit()
    finally:
        db.close()


def _log_error(job_id: int, symbol: str, step: str, exc: Exception):
    db: Session = SessionLocal()
    try:
        e = AutomationError(
            job_id=job_id, symbol=symbol, step=step,
            error_type=type(exc).__name__, error_message=str(exc),
            traceback=traceback.format_exc()[:2000],
        )
        db.add(e); db.commit()
    finally:
        db.close()


# ===== 各ステップ =====
def run_daily_market(market: str = "JP", trigger_type: str = "cron",
                     max_symbols: int = 200, threshold: float = 20.0) -> Dict:
    """市場ごとの日次: 急騰検出 + AAR自動分析"""
    job_id = _create_job("run-daily", market, trigger_type)
    params = {
        "markets": [market], "include_adr": (market == "US"),
        "target_date": date.today().isoformat(),
        "threshold_percent": threshold,
        "max_symbols": max_symbols,
    }
    try:
        # 既存auto_trainingを同期実行 (background でなく同期)
        auto_training._run_sync(params)
        p = auto_training.get_progress()
        _finish_job(job_id, "completed",
                    total_symbols=p.get("total", 0),
                    processed_symbols=p.get("processed", 0),
                    detected_surge_count=p.get("detected", 0),
                    aar_cases_created=p.get("saved", 0),
                    failed_symbols=p.get("failed", 0))
        return {"status": "ok", "job_id": job_id, **p}
    except Exception as e:
        _log_error(job_id, "", "run_daily_market", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "job_id": job_id, "error": str(e)}


def run_screening_and_save_predictions(market: str = "JP", trigger_type: str = "cron",
                                       max_symbols: int = 200, min_score: float = 70,
                                       include_labels: Optional[List[str]] = None) -> Dict:
    """スクリーニング実行→ ranking 上位を prediction_logs に自動保存"""
    from app.services import screener
    from app.services.entry_planner import build_entry_plan

    job_id = _create_job("run-screening-save-predictions", market, trigger_type)
    params = {
        "markets": [market], "include_adr": (market == "US"),
        "use_real_data": True, "price_limit": 3000,
        "min_vol_jp": 30000, "min_vol_us": 100000,
        "max_symbols": max_symbols,
        "use_db_universe": True, "enforce_freshness_gate": True,
        "excluded_symbols": [],
    }
    try:
        screener._run_screening(params)
        results = screener.get_progress().get("results", [])
        if include_labels is None:
            include_labels = ["急騰前夜候補", "条件付き候補"]

        saved = 0
        for r in results:
            if r.get("prediction_label") not in include_labels:
                continue
            if (r.get("final_prediction_score") or 0) < min_score:
                continue
            try:
                ep = build_entry_plan(r)
                prediction_log.save_prediction_log(r, ep)
                saved += 1
            except Exception as e:
                _log_error(job_id, r.get("symbol", ""), "save_log", e)

        _finish_job(job_id, "completed",
                    total_symbols=len(results),
                    processed_symbols=len(results),
                    predictions_saved=saved)
        return {"status": "ok", "job_id": job_id, "predictions_saved": saved,
                "candidates": len(results)}
    except Exception as e:
        _log_error(job_id, "", "screening", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "job_id": job_id, "error": str(e)}


def update_prediction_outcomes(trigger_type: str = "cron") -> Dict:
    job_id = _create_job("update-prediction-outcomes", "ALL", trigger_type)
    try:
        r = prediction_log.update_all_outcomes(limit=200)
        _finish_job(job_id, "completed", outcomes_updated=r.get("updated", 0))
        return {"status": "ok", "job_id": job_id, **r}
    except Exception as e:
        _log_error(job_id, "", "update_outcomes", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def review_predictions(trigger_type: str = "cron") -> Dict:
    job_id = _create_job("review-predictions", "ALL", trigger_type)
    try:
        r = prediction_log.review_all()
        _finish_job(job_id, "completed", reviews_created=r.get("reviewed", 0))
        return {"status": "ok", "job_id": job_id, **r}
    except Exception as e:
        _log_error(job_id, "", "review_predictions", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def save_reviews_as_training(trigger_type: str = "cron") -> Dict:
    job_id = _create_job("save-reviews-as-training", "ALL", trigger_type)
    try:
        r = prediction_log.save_all_reviewed_as_training()
        _finish_job(job_id, "completed", training_cases_created=r.get("saved", 0))
        return {"status": "ok", "job_id": job_id, **r}
    except Exception as e:
        _log_error(job_id, "", "save_reviews_training", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def run_training_builder_known_seed(trigger_type: str = "cron") -> Dict:
    job_id = _create_job("training-builder-known-seed", "BOTH", trigger_type)
    params = {
        "markets": ["JP", "US"], "include_adr": True,
        "max_symbols": 60, "chunk_size": 15,
        "surge_threshold_percent": 20.0, "semi_surge_threshold_percent": 15.0,
        "negative_sample_ratio": 3.0, "target_mode": "known_surge_seed",
    }
    try:
        training_builder.run_build_all_sync(params)
        p = training_builder.get_progress()
        _finish_job(job_id, "completed",
                    total_symbols=p.get("total_symbols", 0),
                    processed_symbols=p.get("processed_symbols", 0),
                    detected_surge_count=p.get("surge_events_found", 0),
                    positive_cases_created=p.get("feature_vectors_created", 0) - p.get("negative_cases_found", 0),
                    negative_cases_created=p.get("negative_cases_found", 0))
        return {"status": "ok", "job_id": job_id, **p}
    except Exception as e:
        _log_error(job_id, "", "training_known_seed", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def run_training_builder_smallcap(trigger_type: str = "cron") -> Dict:
    job_id = _create_job("training-builder-smallcap", "US", trigger_type)
    params = {
        "markets": ["US"], "include_adr": True,
        "max_symbols": 80, "chunk_size": 20,
        "surge_threshold_percent": 20.0, "semi_surge_threshold_percent": 15.0,
        "negative_sample_ratio": 3.0, "target_mode": "us_small_cap_priority",
    }
    try:
        training_builder.run_build_all_sync(params)
        p = training_builder.get_progress()
        _finish_job(job_id, "completed",
                    total_symbols=p.get("total_symbols", 0),
                    processed_symbols=p.get("processed_symbols", 0),
                    detected_surge_count=p.get("surge_events_found", 0),
                    positive_cases_created=p.get("feature_vectors_created", 0) - p.get("negative_cases_found", 0),
                    negative_cases_created=p.get("negative_cases_found", 0))
        return {"status": "ok", "job_id": job_id, **p}
    except Exception as e:
        _log_error(job_id, "", "training_smallcap", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def run_full_daily_pipeline(market: str = "JP", trigger_type: str = "cron") -> Dict:
    """1コマンドで日次全工程"""
    results = {}
    results["run_daily"] = run_daily_market(market, trigger_type)
    results["screening"] = run_screening_and_save_predictions(market, trigger_type, min_score=65)
    results["outcomes"] = update_prediction_outcomes(trigger_type)
    results["review"] = review_predictions(trigger_type)
    results["save_training"] = save_reviews_as_training(trigger_type)
    return {"status": "ok", "market": market, "pipeline": results}


# ===== surge_20 ジョブ =====
def run_surge_20_daily(market: str = "JP", trigger_type: str = "cron", max_symbols: int = 100) -> Dict:
    """日次 surge_20 パイプライン: ランキング生成 → イベント検出 → pre_features抽出"""
    from app.services import surge_20
    job_id = _create_job("surge-20-daily", market, trigger_type)
    try:
        rankings = surge_20.generate_all_rankings(market=market, top_n=50)
        events = surge_20.detect_events_for_universe(market=market, max_symbols=max_symbols)
        features = surge_20.extract_pre_features_for_recent_events(limit=100)
        _finish_job(job_id, "completed",
                    total_symbols=events.get("universe_size", 0),
                    detected_surge_count=events.get("events_saved_new", 0),
                    training_cases_created=features.get("features_created", 0))
        return {"status": "ok", "job_id": job_id,
                "rankings": rankings, "events": events, "features": features}
    except Exception as e:
        _log_error(job_id, "", "surge_20_daily", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def run_one_day_surge_detection(market: str = "JP", trigger_type: str = "cron", max_symbols: int = 150) -> Dict:
    """1日急騰のみを高速検出"""
    from app.services import surge_20, universe_db
    job_id = _create_job("one-day-surge-detection", market, trigger_type)
    try:
        syms = universe_db.list_eligible_yahoo_symbols(
            markets=[market], max_count=max_symbols, include_adr=True
        )
        events = []
        for s in syms:
            try:
                events.extend(surge_20.detect_one_day_surges(s["yahoo_symbol"], s.get("market") or market))
            except Exception as e:
                _log_error(job_id, s["yahoo_symbol"], "one_day_surge_detect", e)
        saved = surge_20._save_surge_events(events, source_type="detected_from_ohlcv")
        _finish_job(job_id, "completed",
                    total_symbols=len(syms),
                    detected_surge_count=saved)
        return {"status": "ok", "job_id": job_id, "events_detected": len(events), "saved": saved}
    except Exception as e:
        _log_error(job_id, "", "one_day_surge_detection", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def run_surge_20_expand_training(market: str = "JP", trigger_type: str = "cron",
                                  max_symbols: int = 300, chunk_size: int = 30,
                                  start_offset: int = 0,
                                  priority_mode: str = "known_surge_first") -> Dict:
    """大規模な教師データ拡張 — chunk処理 + negative生成"""
    from app.services.surge_20 import (
        detect_one_day_surges, detect_multi_day_hit_20, _save_surge_events,
        extract_pre_features_for_recent_events, generate_negative_cases_for_symbol,
    )
    from app.services import universe_db
    from app.services.training_builder import KNOWN_SURGE_SEED_JP, KNOWN_SURGE_SEED_US

    job_id = _create_job(f"surge-20-expand/{priority_mode}", market, trigger_type)
    try:
        # universe選定
        if priority_mode == "known_surge_first":
            if market == "JP":
                seed = [{"symbol": s, "yahoo_symbol": s, "market": "JP"} for s in KNOWN_SURGE_SEED_JP]
            elif market == "US":
                seed = [{"symbol": s, "yahoo_symbol": s, "market": "US"} for s in KNOWN_SURGE_SEED_US]
            else:
                seed = []
            rest = universe_db.list_eligible_yahoo_symbols(
                markets=[market], max_count=0, include_adr=True
            )
            seed_set = {x["symbol"] for x in seed}
            combined = seed + [x for x in rest if x["symbol"] not in seed_set]
            syms = combined[start_offset: start_offset + max_symbols]
        else:
            syms = universe_db.list_eligible_yahoo_symbols(
                markets=[market], max_count=max_symbols + start_offset, include_adr=True
            )[start_offset: start_offset + max_symbols]

        total_events = 0; total_features = 0; total_negatives = 0
        for chunk_start in range(0, len(syms), chunk_size):
            chunk = syms[chunk_start: chunk_start + chunk_size]
            events = []
            for s in chunk:
                try:
                    events.extend(detect_one_day_surges(s["yahoo_symbol"], s.get("market") or market))
                    events.extend(detect_multi_day_hit_20(s["yahoo_symbol"], s.get("market") or market))
                except Exception as e:
                    _log_error(job_id, s["yahoo_symbol"], "detect", e)
            saved = _save_surge_events(events, source_type="detected_from_ohlcv")
            total_events += saved
            try:
                f = extract_pre_features_for_recent_events(limit=200)
                total_features += f.get("features_created", 0)
            except Exception as e:
                _log_error(job_id, "", "extract_features", e)
            for s in chunk:
                try:
                    total_negatives += generate_negative_cases_for_symbol(
                        s["yahoo_symbol"], s.get("market") or market, max_cases=15
                    )
                except Exception as e:
                    _log_error(job_id, s.get("symbol"), "neg_gen", e)

        _finish_job(job_id, "completed",
                    total_symbols=len(syms),
                    detected_surge_count=total_events,
                    positive_cases_created=total_features,
                    negative_cases_created=total_negatives)
        return {"status": "ok", "job_id": job_id,
                "symbols_processed": len(syms),
                "events_saved": total_events,
                "features_created": total_features,
                "negatives_created": total_negatives}
    except Exception as e:
        _log_error(job_id, "", "expand_training", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


def run_surge_20_candidate_build(market: str = "JP", trigger_type: str = "cron", max_symbols: int = 200) -> Dict:
    from app.services import surge_20
    job_id = _create_job("surge-20-candidate-build", market, trigger_type)
    try:
        r = surge_20.build_candidates(market=market, max_symbols=max_symbols)
        _finish_job(job_id, "completed",
                    total_symbols=r.get("universe_scanned", 0),
                    detected_surge_count=r.get("candidates_count", 0))
        return {"status": "ok", "job_id": job_id, **r}
    except Exception as e:
        _log_error(job_id, "", "surge_20_candidate_build", e)
        _finish_job(job_id, "failed", error_message=str(e))
        return {"status": "failed", "error": str(e)}


# ===== サマリ =====
def get_automation_status() -> Dict:
    from zoneinfo import ZoneInfo
    db: Session = SessionLocal()
    try:
        from sqlalchemy import desc
        latest = db.query(AutomationJob).order_by(desc(AutomationJob.id)).first()
        latest_success = (db.query(AutomationJob)
                          .filter(AutomationJob.status == "completed")
                          .order_by(desc(AutomationJob.id)).first())
        latest_failure = (db.query(AutomationJob)
                          .filter(AutomationJob.status == "failed")
                          .order_by(desc(AutomationJob.id)).first())
        running = db.query(AutomationJob).filter(AutomationJob.status == "running").count()

        # JST基準の今日 (UTC越境対策)
        jst = ZoneInfo("Asia/Tokyo")
        now_jst = datetime.now(jst)
        today_start_utc = datetime(now_jst.year, now_jst.month, now_jst.day, tzinfo=jst).astimezone(ZoneInfo("UTC")).replace(tzinfo=None)
        today_jobs = (db.query(AutomationJob)
                      .filter(AutomationJob.started_at >= today_start_utc)
                      .all())
        today_summary = {
            "jobs_today": len(today_jobs),
            "surge_detected_today": sum(j.detected_surge_count or 0 for j in today_jobs),
            "aar_cases_today": sum(j.aar_cases_created or 0 for j in today_jobs),
            "positive_cases_today": sum(j.positive_cases_created or 0 for j in today_jobs),
            "negative_cases_today": sum(j.negative_cases_created or 0 for j in today_jobs),
            "predictions_saved_today": sum(j.predictions_saved or 0 for j in today_jobs),
            "outcomes_updated_today": sum(j.outcomes_updated or 0 for j in today_jobs),
            "training_cases_today": sum(j.training_cases_created or 0 for j in today_jobs),
        }

        cron_secret_env = bool(os.getenv("CRON_SECRET"))
        cron_secret_db = bool(_get_setting("cron_secret_marker"))
        return {
            "automation_enabled": _get_setting("automation_enabled", "true") == "true",
            # 後方互換用 (既存UIが見ているフィールド)
            "cron_secret_configured": cron_secret_env,
            # 細分化された状態
            "cron_secret_env_configured": cron_secret_env,
            "cron_secret_db_configured": cron_secret_db,
            "cron_secret_effective_configured": cron_secret_env,
            "cron_secret_source": "render_env" if cron_secret_env else None,
            "github_actions_workflow_exists": True,
            "github_actions_secrets_note": "GitHub側Secretsはbackendから直接確認できません。/api/automation/test-cron-secret で接続テストしてください。",
            "latest_job_id": latest.id if latest else None,
            "latest_job_type": latest.job_type if latest else None,
            "latest_run_at": latest.started_at.isoformat() if latest and latest.started_at else None,
            "latest_success_at": latest_success.started_at.isoformat() if latest_success else None,
            "latest_failure_at": latest_failure.started_at.isoformat() if latest_failure else None,
            "running_jobs": running,
            "today": today_summary,
            "today_summary": today_summary,
            "training_data_balance": _get_training_balance(),
        }
    finally:
        db.close()


def _get_training_balance() -> Dict:
    from app.models.models import TrainingFeatureVector
    db: Session = SessionLocal()
    try:
        total = db.query(TrainingFeatureVector).count()
        if total == 0:
            return {"total": 0, "positive": 0, "negative": 0, "ratio": 0}
        positive = db.query(TrainingFeatureVector).filter(
            TrainingFeatureVector.case_type.in_(["positive_surge", "semi_positive_surge"])
        ).count()
        negative = total - positive
        return {
            "total": total,
            "positive": positive,
            "negative": negative,
            "ratio": round(negative / max(1, positive), 2),
        }
    finally:
        db.close()


def list_jobs(limit: int = 50) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        rows = db.query(AutomationJob).order_by(AutomationJob.id.desc()).limit(limit).all()
        return [{
            "id": j.id, "job_type": j.job_type, "market": j.market,
            "status": j.status, "trigger_type": j.trigger_type,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
            "duration_seconds": j.duration_seconds,
            "total_symbols": j.total_symbols,
            "processed_symbols": j.processed_symbols,
            "detected_surge_count": j.detected_surge_count,
            "positive_cases_created": j.positive_cases_created,
            "negative_cases_created": j.negative_cases_created,
            "aar_cases_created": j.aar_cases_created,
            "predictions_saved": j.predictions_saved,
            "outcomes_updated": j.outcomes_updated,
            "reviews_created": j.reviews_created,
            "training_cases_created": j.training_cases_created,
            "error_message": j.error_message,
        } for j in rows]
    finally:
        db.close()


def list_errors(limit: int = 50) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        rows = db.query(AutomationError).order_by(AutomationError.id.desc()).limit(limit).all()
        return [{
            "id": e.id, "job_id": e.job_id, "symbol": e.symbol,
            "step": e.step, "error_type": e.error_type,
            "error_message": e.error_message,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        } for e in rows]
    finally:
        db.close()


def _get_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    db: Session = SessionLocal()
    try:
        r = db.query(AutomationSetting).filter(AutomationSetting.key == key).first()
        return r.value if r else default
    finally:
        db.close()


def set_setting(key: str, value: str):
    db: Session = SessionLocal()
    try:
        r = db.query(AutomationSetting).filter(AutomationSetting.key == key).first()
        if r:
            r.value = value
        else:
            db.add(AutomationSetting(key=key, value=value))
        db.commit()
    finally:
        db.close()
