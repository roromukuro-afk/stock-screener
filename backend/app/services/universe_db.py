"""ユニバース・価格鮮度のDB永続化レイヤ"""
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.models import (
    UniverseSymbol, PriceFreshness, UniverseUpdateJob, UniverseSourceFile
)


def upsert_universe_items(items: List[Dict], source_tag: str = None) -> Dict:
    """ユニバース銘柄をupsertし、件数を返す"""
    db: Session = SessionLocal()
    inserted = 0
    updated = 0
    try:
        existing_symbols = {s[0] for s in db.query(UniverseSymbol.symbol).all()}
        now = datetime.utcnow()

        for item in items:
            sym = item["symbol"]
            data = {
                "raw_symbol": item.get("raw_symbol"),
                "symbol": sym,
                "yahoo_symbol": item.get("yahoo_symbol"),
                "name": item.get("name"),
                "market": item.get("market"),
                "exchange": item.get("exchange"),
                "source": item.get("source"),
                "country": item.get("country"),
                "currency": item.get("currency"),
                "instrument_type": item.get("instrument_type"),
                "is_common_stock": item.get("is_common_stock", False),
                "is_adr": item.get("is_adr", False),
                "is_etf": item.get("is_etf", False),
                "is_warrant": item.get("is_warrant", False),
                "is_unit": item.get("is_unit", False),
                "is_right": item.get("is_right", False),
                "is_preferred": item.get("is_preferred", False),
                "is_spac": item.get("is_spac", False),
                "is_fund": item.get("is_fund", False),
                "is_test_issue": item.get("is_test_issue", False),
                "is_screening_eligible": item.get("is_screening_eligible", False),
                "exclusion_reason": item.get("exclusion_reason"),
                "duplicate_key": item.get("duplicate_key", sym),
                "last_seen_at": now,
                "last_updated_at": now,
            }
            if sym in existing_symbols:
                db.query(UniverseSymbol).filter(UniverseSymbol.symbol == sym).update(data)
                updated += 1
            else:
                row = UniverseSymbol(**data, first_seen_at=now)
                db.add(row)
                inserted += 1

        db.commit()
        return {"inserted": inserted, "updated": updated}
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_universe_source_file(meta: Dict) -> int:
    db: Session = SessionLocal()
    try:
        f = UniverseSourceFile(
            source=meta.get("source"),
            source_url=meta.get("source_url"),
            file_name=meta.get("file_name"),
            row_count=meta.get("row_count", 0),
            checksum=meta.get("checksum"),
            file_creation_time=meta.get("file_creation_time"),
            status=meta.get("status"),
            error_message=meta.get("error"),
        )
        db.add(f)
        db.commit()
        return f.id
    finally:
        db.close()


def get_universe_summary() -> Dict:
    db: Session = SessionLocal()
    try:
        total = db.query(UniverseSymbol).count()
        if total == 0:
            return {
                "total": 0,
                "by_market": {},
                "by_source": {},
                "by_instrument_type": {},
                "eligible_count": 0,
                "common_stock_count": 0,
                "adr_count": 0,
                "etf_count": 0,
                "warrant_count": 0,
                "unit_count": 0,
                "right_count": 0,
                "preferred_count": 0,
                "test_issue_count": 0,
                "fund_count": 0,
            }
        by_market = dict(db.query(UniverseSymbol.market, _count()).group_by(UniverseSymbol.market).all())
        by_source = dict(db.query(UniverseSymbol.source, _count()).group_by(UniverseSymbol.source).all())
        by_type = dict(db.query(UniverseSymbol.instrument_type, _count()).group_by(UniverseSymbol.instrument_type).all())

        return {
            "total": total,
            "by_market": by_market,
            "by_source": by_source,
            "by_instrument_type": by_type,
            "eligible_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_screening_eligible == True).count(),
            "common_stock_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_common_stock == True).count(),
            "adr_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_adr == True).count(),
            "etf_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_etf == True).count(),
            "warrant_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_warrant == True).count(),
            "unit_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_unit == True).count(),
            "right_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_right == True).count(),
            "preferred_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_preferred == True).count(),
            "test_issue_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_test_issue == True).count(),
            "fund_count": db.query(UniverseSymbol).filter(UniverseSymbol.is_fund == True).count(),
        }
    finally:
        db.close()


def list_universe(eligible_only: bool = False, market: str = None, limit: int = 1000, offset: int = 0) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        q = db.query(UniverseSymbol)
        if eligible_only:
            q = q.filter(UniverseSymbol.is_screening_eligible == True)
        if market:
            q = q.filter(UniverseSymbol.market == market)
        total = q.count()
        rows = q.order_by(UniverseSymbol.market, UniverseSymbol.symbol).limit(limit).offset(offset).all()
        return {
            "total": total,
            "limit": limit,
            "offset": offset,
            "items": [_to_dict(r) for r in rows],
        }
    finally:
        db.close()


def list_eligible_yahoo_symbols(markets: List[str] = None, max_count: int = 0, include_adr: bool = True) -> List[Dict]:
    """スクリーニング対象として有効な銘柄のyahoo_symbolリスト"""
    db: Session = SessionLocal()
    try:
        q = db.query(UniverseSymbol).filter(UniverseSymbol.is_screening_eligible == True)
        if markets:
            q = q.filter(UniverseSymbol.market.in_(markets))
        if not include_adr:
            q = q.filter(UniverseSymbol.is_adr == False)
        if max_count > 0:
            q = q.limit(max_count)
        return [
            {
                "symbol": r.symbol,
                "yahoo_symbol": r.yahoo_symbol or r.symbol,
                "name": r.name,
                "market": r.market,
                "is_adr": r.is_adr,
                "currency": r.currency,
            }
            for r in q.all()
        ]
    finally:
        db.close()


def save_price_freshness(symbol: str, market: str, fresh_data: Dict) -> int:
    db: Session = SessionLocal()
    try:
        f = PriceFreshness(
            symbol=symbol,
            yahoo_symbol=symbol,
            market=market,
            data_source=fresh_data.get("data_source"),
            price=fresh_data.get("price"),
            currency=fresh_data.get("currency"),
            jpy_price=fresh_data.get("jpy_price"),
            quote_date=fresh_data.get("quote_date"),
            quote_time=fresh_data.get("quote_time"),
            latest_trading_day=fresh_data.get("latest_trading_day"),
            fetched_at_utc=fresh_data.get("fetched_at_utc"),
            fetched_at_jst=fresh_data.get("fetched_at_jst"),
            exchange_timezone=fresh_data.get("exchange_timezone"),
            is_market_open_at_fetch=fresh_data.get("is_market_open_at_fetch"),
            delay_minutes_estimated=fresh_data.get("delay_minutes_estimated"),
            is_realtime_or_delayed=fresh_data.get("is_realtime_or_delayed"),
            freshness_status=fresh_data.get("freshness_status"),
            is_stale=fresh_data.get("is_stale", False),
            stale_reason=fresh_data.get("stale_reason"),
        )
        db.add(f)
        db.commit()
        return f.id
    finally:
        db.close()


def get_freshness_summary() -> Dict:
    from sqlalchemy import func
    db: Session = SessionLocal()
    try:
        total = db.query(PriceFreshness).count()
        fresh = db.query(PriceFreshness).filter(PriceFreshness.is_stale == False).count()
        stale = db.query(PriceFreshness).filter(PriceFreshness.is_stale == True).count()
        by_status = dict(
            db.query(PriceFreshness.freshness_status, func.count(PriceFreshness.id))
              .group_by(PriceFreshness.freshness_status).all()
        )
        return {
            "total": total,
            "fresh_count": fresh,
            "stale_count": stale,
            "by_freshness_status": by_status,
        }
    finally:
        db.close()


def list_stale_prices(limit: int = 500) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        rows = (db.query(PriceFreshness)
                .filter(PriceFreshness.is_stale == True)
                .order_by(PriceFreshness.id.desc()).limit(limit).all())
        return [
            {
                "symbol": r.symbol,
                "market": r.market,
                "quote_date": r.quote_date,
                "freshness_status": r.freshness_status,
                "stale_reason": r.stale_reason,
                "fetched_at_jst": r.fetched_at_jst,
            } for r in rows
        ]
    finally:
        db.close()


def create_update_job(source: str) -> int:
    db: Session = SessionLocal()
    try:
        j = UniverseUpdateJob(status="running", source=source)
        db.add(j)
        db.commit()
        return j.id
    finally:
        db.close()


def complete_update_job(job_id: int, summary: Dict, status: str = "completed", error: str = None):
    db: Session = SessionLocal()
    try:
        j = db.query(UniverseUpdateJob).filter(UniverseUpdateJob.id == job_id).first()
        if not j:
            return
        j.status = status
        j.total_raw_count = summary.get("total_raw_count", 0)
        j.normalized_count = summary.get("normalized_count", 0)
        j.eligible_count = summary.get("eligible_count", 0)
        j.excluded_count = summary.get("excluded_count", 0)
        j.stale_price_count = summary.get("stale_price_count", 0)
        j.fresh_price_count = summary.get("fresh_price_count", 0)
        j.failed_price_count = summary.get("failed_price_count", 0)
        j.error_message = error
        j.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


def latest_update_jobs(limit: int = 10) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        rows = db.query(UniverseUpdateJob).order_by(UniverseUpdateJob.id.desc()).limit(limit).all()
        return [
            {
                "id": r.id,
                "status": r.status,
                "source": r.source,
                "total_raw_count": r.total_raw_count,
                "normalized_count": r.normalized_count,
                "eligible_count": r.eligible_count,
                "excluded_count": r.excluded_count,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "error_message": r.error_message,
            } for r in rows
        ]
    finally:
        db.close()


def _count():
    from sqlalchemy import func
    return func.count(UniverseSymbol.id)


def _to_dict(r: UniverseSymbol) -> Dict:
    return {
        "symbol": r.symbol,
        "yahoo_symbol": r.yahoo_symbol,
        "name": r.name,
        "market": r.market,
        "exchange": r.exchange,
        "source": r.source,
        "country": r.country,
        "currency": r.currency,
        "instrument_type": r.instrument_type,
        "is_common_stock": r.is_common_stock,
        "is_adr": r.is_adr,
        "is_etf": r.is_etf,
        "is_warrant": r.is_warrant,
        "is_unit": r.is_unit,
        "is_right": r.is_right,
        "is_preferred": r.is_preferred,
        "is_test_issue": r.is_test_issue,
        "is_screening_eligible": r.is_screening_eligible,
        "exclusion_reason": r.exclusion_reason,
        "last_updated_at": r.last_updated_at.isoformat() if r.last_updated_at else None,
    }
