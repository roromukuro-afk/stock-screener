"""DB永続化レイヤ"""
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.models import (
    ScreeningResult, ExclusionList, AARRecord,
    AppSetting, ScreeningJob, Stock
)


def save_screening_run(results: List[Dict], exclusions: List[Dict],
                       markets: List[str], include_adr: bool) -> int:
    """スクリーニング結果一式をDBに保存。jobレコードIDを返す"""
    db: Session = SessionLocal()
    try:
        # ジョブレコード作成
        adopted = len([r for r in results if r.get("classification") == "採用候補"])
        conditional = len([r for r in results if r.get("classification") == "条件付き候補"])
        watch = len([r for r in results if r.get("classification") == "監視候補"])

        job = ScreeningJob(
            status="completed",
            market_scope=",".join(markets) + (",ADR" if include_adr else ""),
            total_count=len(results) + len(exclusions),
            processed_count=len(results) + len(exclusions),
            adopted_count=adopted,
            conditional_count=conditional,
            watch_count=watch,
            excluded_count=len(exclusions),
            finished_at=datetime.now(),
        )
        db.add(job)
        db.flush()
        job_id = job.id

        # 前回の同日スクリーニング結果を削除して上書き
        today = datetime.now().date().isoformat()
        db.query(ScreeningResult).filter(ScreeningResult.date == today).delete()

        for r in results:
            row = ScreeningResult(
                symbol=r.get("symbol"),
                date=r.get("date", today),
                price=r.get("price"),
                jpy_price=r.get("jpy_price"),
                fx_rate=r.get("fx_rate"),
                fx_rate_timestamp=r.get("fx_rate_timestamp"),
                price_timestamp=r.get("price_timestamp"),
                market_cap=r.get("market_cap"),
                volume=r.get("volume"),
                turnover=r.get("turnover"),
                price_condition_pass=True,
                liquidity_condition_pass=True,
                upside_score=r.get("upside_score", 0),
                future_catalyst_score=r.get("future_catalyst_score", 0),
                chart_score=r.get("chart_score", 0),
                volume_cycle_score=r.get("volume_cycle_score", 0),
                material_theme_score=r.get("material_theme_score", 0),
                supply_score=r.get("supply_score", 0),
                archetype_score=r.get("archetype_score", 0),
                risk_management_score=r.get("risk_management_score", 0),
                total_score=r.get("total_score", 0),
                classification=r.get("classification"),
                volume_cycle_state=r.get("volume_cycle_state"),
                chart_cycle_state=r.get("chart_cycle_state"),
                main_archetype=r.get("main_archetype"),
                sub_archetypes=r.get("sub_archetypes", []),
                chart_types=r.get("chart_types", []),
                warning_types=r.get("warning_types", []),
                warning_flags=r.get("warning_flags", []),
                exclude_flag=False,
                ai_comment=r.get("ai_comment"),
            )
            db.add(row)

        for e in exclusions:
            row = ScreeningResult(
                symbol=e.get("symbol"),
                date=e.get("date", today),
                price=e.get("price"),
                volume=e.get("volume"),
                price_condition_pass=False,
                liquidity_condition_pass=False,
                total_score=0,
                classification="除外",
                exclude_flag=True,
                exclude_reason=e.get("exclude_reason"),
            )
            db.add(row)

        db.commit()
        return job_id
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


def get_latest_screening_results(date: str = None, limit: int = 1000) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        q = db.query(ScreeningResult).filter(ScreeningResult.exclude_flag == False)
        if date:
            q = q.filter(ScreeningResult.date == date)
        else:
            latest = db.query(ScreeningResult.date).order_by(ScreeningResult.date.desc()).first()
            if latest:
                q = q.filter(ScreeningResult.date == latest[0])
        q = q.order_by(ScreeningResult.total_score.desc()).limit(limit)
        return [_row_to_dict(r) for r in q.all()]
    finally:
        db.close()


def get_latest_exclusions(limit: int = 1000) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        latest = db.query(ScreeningResult.date).order_by(ScreeningResult.date.desc()).first()
        if not latest:
            return []
        q = (db.query(ScreeningResult)
             .filter(ScreeningResult.date == latest[0])
             .filter(ScreeningResult.exclude_flag == True)
             .limit(limit))
        return [_row_to_dict(r) for r in q.all()]
    finally:
        db.close()


def _row_to_dict(r: ScreeningResult) -> Dict:
    return {
        "symbol": r.symbol,
        "date": r.date,
        "price": r.price,
        "jpy_price": r.jpy_price,
        "volume": r.volume,
        "total_score": r.total_score,
        "classification": r.classification,
        "volume_cycle_state": r.volume_cycle_state,
        "chart_cycle_state": r.chart_cycle_state,
        "main_archetype": r.main_archetype,
        "exclude_flag": r.exclude_flag,
        "exclude_reason": r.exclude_reason,
        "ai_comment": r.ai_comment,
    }


# Exclusion list
def list_exclusion_entries() -> List[Dict]:
    db: Session = SessionLocal()
    try:
        rows = db.query(ExclusionList).all()
        return [{"symbol": r.symbol, "name": r.name, "market": r.market, "reason": r.reason} for r in rows]
    finally:
        db.close()


def add_exclusion_entry(symbol: str, name: str = "", market: str = "", reason: str = "手動登録") -> bool:
    db: Session = SessionLocal()
    try:
        existing = db.query(ExclusionList).filter(ExclusionList.symbol == symbol).first()
        if existing:
            return False
        db.add(ExclusionList(symbol=symbol, name=name, market=market, reason=reason))
        db.commit()
        return True
    finally:
        db.close()


def remove_exclusion_entry(symbol: str) -> bool:
    db: Session = SessionLocal()
    try:
        count = db.query(ExclusionList).filter(ExclusionList.symbol == symbol).delete()
        db.commit()
        return count > 0
    finally:
        db.close()


# App settings
def get_setting(key: str, default: str = None) -> Optional[str]:
    db: Session = SessionLocal()
    try:
        s = db.query(AppSetting).filter(AppSetting.key == key).first()
        return s.value if s else default
    finally:
        db.close()


def set_setting(key: str, value: str):
    db: Session = SessionLocal()
    try:
        s = db.query(AppSetting).filter(AppSetting.key == key).first()
        if s:
            s.value = value
        else:
            db.add(AppSetting(key=key, value=value))
        db.commit()
    finally:
        db.close()


def get_all_settings() -> Dict[str, str]:
    db: Session = SessionLocal()
    try:
        rows = db.query(AppSetting).all()
        return {r.key: r.value for r in rows}
    finally:
        db.close()


def latest_job() -> Optional[Dict]:
    db: Session = SessionLocal()
    try:
        j = db.query(ScreeningJob).order_by(ScreeningJob.id.desc()).first()
        if not j:
            return None
        return {
            "id": j.id,
            "status": j.status,
            "market_scope": j.market_scope,
            "total_count": j.total_count,
            "adopted_count": j.adopted_count,
            "conditional_count": j.conditional_count,
            "watch_count": j.watch_count,
            "excluded_count": j.excluded_count,
            "started_at": j.started_at.isoformat() if j.started_at else None,
            "finished_at": j.finished_at.isoformat() if j.finished_at else None,
        }
    finally:
        db.close()


# Backtest
def save_aar_record(record: Dict) -> int:
    db: Session = SessionLocal()
    try:
        r = AARRecord(**{k: v for k, v in record.items() if hasattr(AARRecord, k)})
        db.add(r)
        db.commit()
        return r.id
    finally:
        db.close()
