"""自動教師データ収集エンジン

DBユニバースから直近営業日の前日比+N%以上を検出し、
AAR分析エンジンに自動投入する。重複は防止。
"""
import threading
from typing import List, Dict, Optional
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models.models import (
    AutoTrainingJob, AutoTrainingResult, AARAnalysisCase
)
from app.services import universe_db, aar_analyzer, aar_db
from app.services.price_fetcher import get_stock_data


_progress: Dict = {"running": False, "status": "idle", "processed": 0, "total": 0,
                   "detected": 0, "saved": 0, "duplicate": 0, "failed": 0, "job_id": None}
_lock = threading.Lock()


def get_progress() -> Dict:
    with _lock:
        return dict(_progress)


def _detect_surges(
    markets: List[str],
    target_date: str,
    threshold_percent: float = 20.0,
    max_symbols: int = 500,
    include_adr: bool = True,
) -> List[Dict]:
    """ユニバースから target_date 前後で +threshold% 以上動いた銘柄を抽出"""
    syms = universe_db.list_eligible_yahoo_symbols(
        markets=markets, max_count=max_symbols, include_adr=include_adr
    )
    surges = []
    for s in syms:
        sym = s["yahoo_symbol"]
        market = s.get("market", "JP")
        df = get_stock_data(sym, period="1mo", market=market)
        if df is None or len(df) < 2:
            continue
        df = df.sort_values("date").reset_index(drop=True)
        # target_date またはそれに最も近い日のインデックス
        match = df[df["date"].astype(str) == target_date]
        if match.empty:
            df_filt = df[df["date"].astype(str) <= target_date]
            if df_filt.empty:
                continue
            t0_idx = int(df_filt.index[-1])
        else:
            t0_idx = int(match.index[0])
        if t0_idx < 1:
            continue
        t0_close = float(df.iloc[t0_idx]["close"])
        t_prev_close = float(df.iloc[t0_idx - 1]["close"])
        if t_prev_close <= 0:
            continue
        move = (t0_close - t_prev_close) / t_prev_close * 100
        if move >= threshold_percent:
            surges.append({
                "symbol": sym,
                "name": s.get("name", sym),
                "market": market,
                "move_date": str(df.iloc[t0_idx]["date"]),
                "move_percent": round(move, 2),
            })
    return surges


def _is_duplicate(symbol: str, move_date: str) -> bool:
    db: Session = SessionLocal()
    try:
        existing = (db.query(AARAnalysisCase)
                    .filter(AARAnalysisCase.symbol == symbol)
                    .filter(AARAnalysisCase.move_date == move_date)
                    .first())
        return existing is not None
    finally:
        db.close()


def _run_sync(params: Dict):
    global _progress
    with _lock:
        _progress.update({
            "running": True, "status": "running", "processed": 0,
            "total": 0, "detected": 0, "saved": 0, "duplicate": 0, "failed": 0, "job_id": None,
        })

    markets = params.get("markets") or ["JP", "US"]
    target_date = params.get("target_date") or date.today().isoformat()
    threshold = float(params.get("threshold_percent", 20.0))
    max_symbols = int(params.get("max_symbols", 500))
    include_adr = bool(params.get("include_adr", True))
    market_scope = ",".join(markets) + (",ADR" if include_adr else "")

    db: Session = SessionLocal()
    try:
        job = AutoTrainingJob(
            status="running",
            target_date=target_date,
            market_scope=market_scope,
            threshold_percent=threshold,
        )
        db.add(job)
        db.commit()
        job_id = job.id
    finally:
        db.close()

    with _lock:
        _progress["job_id"] = job_id

    try:
        # 1. 急騰銘柄検出
        surges = _detect_surges(markets, target_date, threshold, max_symbols, include_adr)
        with _lock:
            _progress["total"] = len(surges)
            _progress["detected"] = len(surges)

        # 2. 各銘柄をAAR分析
        for s in surges:
            sym, market, mv_date, mv_pct = s["symbol"], s["market"], s["move_date"], s["move_percent"]
            duplicate = _is_duplicate(sym, mv_date)

            result_row = {
                "job_id": job_id,
                "symbol": sym,
                "market": market,
                "target_date": mv_date,
                "move_percent": mv_pct,
                "detected_as_surge": True,
                "duplicate": duplicate,
            }

            if duplicate:
                with _lock:
                    _progress["duplicate"] += 1
                    _progress["processed"] += 1
                _save_result_row(result_row, analyzed=False, saved=False)
                continue

            try:
                case = aar_analyzer.analyze_surge_case(
                    symbol=sym, market=market, move_date=mv_date,
                    move_percent_user=mv_pct, name=s.get("name"),
                )
                if case.get("status") != "ok":
                    with _lock:
                        _progress["failed"] += 1
                        _progress["processed"] += 1
                    result_row["analyzed"] = False
                    result_row["error_message"] = case.get("error")
                    _save_result_row(result_row, analyzed=False, saved=False)
                    continue

                input_id = aar_db.save_input_case(
                    symbol=sym, market=market, move_date=mv_date,
                    yahoo_symbol=case.get("yahoo_symbol"), name=case.get("name"),
                    move_percent_user=mv_pct, source_file="auto_training",
                )
                case_id = aar_db.save_analysis_case(input_id, case)
                aar_db.save_snapshots(case_id, case["symbol"], case.get("snapshots", []))
                aar_db.save_feature_vector(case_id, case)
                aar_db.update_input_status(input_id, "analyzed")

                result_row["analyzed"] = True
                result_row["saved_to_training"] = True
                result_row["aar_case_id"] = case_id
                result_row["catalyst_category"] = case.get("catalyst_category")
                result_row["t1_judgement"] = case.get("t1_judgement")
                _save_result_row(result_row, analyzed=True, saved=True)

                with _lock:
                    _progress["saved"] += 1
                    _progress["processed"] += 1
            except Exception as e:
                with _lock:
                    _progress["failed"] += 1
                    _progress["processed"] += 1
                result_row["error_message"] = str(e)
                _save_result_row(result_row, analyzed=False, saved=False)

        # ジョブ完了
        db2: Session = SessionLocal()
        try:
            jr = db2.query(AutoTrainingJob).filter(AutoTrainingJob.id == job_id).first()
            if jr:
                p = get_progress()
                jr.status = "completed"
                jr.total_universe_count = len(surges)
                jr.surge_detected_count = p["detected"]
                jr.analyzed_count = p["saved"] + p["failed"]
                jr.saved_case_count = p["saved"]
                jr.duplicate_count = p["duplicate"]
                jr.failed_count = p["failed"]
                jr.finished_at = datetime.utcnow()
                db2.commit()
        finally:
            db2.close()

        with _lock:
            _progress["running"] = False
            _progress["status"] = "completed"
    except Exception as e:
        with _lock:
            _progress["running"] = False
            _progress["status"] = "failed"
            _progress["error"] = str(e)


def _save_result_row(row: Dict, analyzed: bool, saved: bool):
    db: Session = SessionLocal()
    try:
        r = AutoTrainingResult(
            job_id=row.get("job_id"),
            symbol=row.get("symbol"),
            market=row.get("market"),
            target_date=row.get("target_date"),
            move_percent=row.get("move_percent"),
            detected_as_surge=True,
            analyzed=analyzed,
            saved_to_training=saved,
            duplicate=row.get("duplicate", False),
            aar_case_id=row.get("aar_case_id"),
            catalyst_category=row.get("catalyst_category"),
            t1_judgement=row.get("t1_judgement"),
            error_message=row.get("error_message"),
        )
        db.add(r)
        db.commit()
    finally:
        db.close()


def run_in_background(params: Dict):
    t = threading.Thread(target=_run_sync, args=(params,), daemon=True)
    t.start()


def list_jobs(limit: int = 30) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        rows = db.query(AutoTrainingJob).order_by(AutoTrainingJob.id.desc()).limit(limit).all()
        return [{
            "id": r.id,
            "status": r.status,
            "target_date": r.target_date,
            "market_scope": r.market_scope,
            "threshold_percent": r.threshold_percent,
            "surge_detected_count": r.surge_detected_count,
            "saved_case_count": r.saved_case_count,
            "duplicate_count": r.duplicate_count,
            "failed_count": r.failed_count,
            "started_at": r.started_at.isoformat() if r.started_at else None,
            "finished_at": r.finished_at.isoformat() if r.finished_at else None,
        } for r in rows]
    finally:
        db.close()


def list_results(job_id: Optional[int] = None, limit: int = 500) -> Dict:
    db: Session = SessionLocal()
    try:
        q = db.query(AutoTrainingResult)
        if job_id:
            q = q.filter(AutoTrainingResult.job_id == job_id)
        total = q.count()
        rows = q.order_by(AutoTrainingResult.id.desc()).limit(limit).all()
        return {
            "total": total,
            "items": [{
                "id": r.id,
                "job_id": r.job_id,
                "symbol": r.symbol,
                "market": r.market,
                "target_date": r.target_date,
                "move_percent": r.move_percent,
                "analyzed": r.analyzed,
                "saved_to_training": r.saved_to_training,
                "duplicate": r.duplicate,
                "aar_case_id": r.aar_case_id,
                "catalyst_category": r.catalyst_category,
                "t1_judgement": r.t1_judgement,
                "error_message": r.error_message,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            } for r in rows]
        }
    finally:
        db.close()
