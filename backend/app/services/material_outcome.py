"""MaterialEvent (材料) → 株価結果 (outcome) を自動計算・検証する。

各材料イベントについて publish_at 後の OHLCV (historical_ohlcv DB キャッシュ) から
T+1/3/5/10/20 終値、max_gain/drawdown、20%到達日数を算出して MaterialOutcome に保存。
カテゴリ×ソース別の hit rate / avg gain を集計して、AI の catalyst_boost に
empirical な根拠を与える。
"""
from typing import Dict, List, Optional
from datetime import date, timedelta
import logging

from sqlalchemy import func as _f
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.models import MaterialEvent, MaterialOutcome, HistoricalOHLCV

logger = logging.getLogger(__name__)


def _yahoo_symbol(sym: str, market: str) -> str:
    if not sym:
        return sym
    if market == "JP" and not sym.endswith(".T") and not sym.endswith(".JP"):
        return f"{sym}.T"
    return sym


def _load_history(symbol: str) -> List[Dict]:
    """historical_ohlcv から取得。複数 symbol 形式を試し、無ければ live yfinance fallback。"""
    # symbol / yahoo_symbol いずれの形式でも当たるよう複数キーで検索
    candidates = [symbol]
    if symbol.endswith(".T"):
        candidates.append(symbol[:-2])  # 4桁コード
    elif "." not in symbol:
        candidates.append(f"{symbol}.T")
    db = SessionLocal()
    try:
        for try_sym in candidates:
            rows = (db.query(HistoricalOHLCV)
                    .filter((HistoricalOHLCV.symbol == try_sym) |
                            (HistoricalOHLCV.yahoo_symbol == try_sym))
                    .order_by(HistoricalOHLCV.date).all())
            if rows and len(rows) >= 30:
                return [{"date": r.date, "close": r.close,
                         "high": r.high, "low": r.low,
                         "open": r.open, "volume": r.volume} for r in rows]
    finally:
        db.close()
    # フォールバック: 3ヶ月分を live 取得して historical_ohlcv にキャッシュ (Render-safe・1銘柄ぶん)
    try:
        from app.services.price_fetcher import get_stock_data
        df = get_stock_data(symbol, period="6mo")
        if df is None or len(df) < 30:
            return []
        df = df.sort_values("date").reset_index(drop=True)
        # キャッシュへ書き戻し (idempotent)
        db = SessionLocal()
        try:
            for _, r in df.iterrows():
                d_str = str(r.get("date") or "")[:10]
                if not d_str:
                    continue
                exists = (db.query(HistoricalOHLCV.id)
                          .filter(HistoricalOHLCV.symbol == symbol)
                          .filter(HistoricalOHLCV.date == d_str).first())
                if exists:
                    continue
                db.add(HistoricalOHLCV(
                    symbol=symbol, yahoo_symbol=symbol, date=d_str,
                    open=float(r.get("open") or 0) or None,
                    high=float(r.get("high") or 0) or None,
                    low=float(r.get("low") or 0) or None,
                    close=float(r.get("close") or 0) or None,
                    volume=float(r.get("volume") or 0) or None,
                    data_source="live_yfinance_fallback",
                ))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()
        return df.to_dict(orient="records")
    except Exception as e:
        logger.warning(f"_load_history live fallback {symbol} failed: {e}")
        return []


def _normalize_date(s: str) -> Optional[str]:
    """RSS pubDate / ISO / YYYY-MM-DD いずれも YYYY-MM-DD に。失敗時 None。"""
    if not s:
        return None
    s = s.strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-" and s[:4].isdigit():
        return s[:10]
    if "T" in s and s.split("T")[0].count("-") == 2:
        return s.split("T")[0]
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt:
            return dt.date().isoformat()
    except Exception:
        pass
    return None


def _find_index_at_or_after(rows: List[Dict], target_date: str) -> Optional[int]:
    """target_date 以降の最初の取引日 index"""
    for i, r in enumerate(rows):
        if str(r["date"]) >= target_date:
            return i
    return None


def compute_outcome_for_event(ev: MaterialEvent) -> Optional[Dict]:
    """1件の MaterialEvent について outcome 指標を計算 (historical_ohlcv 必須)"""
    sym = _yahoo_symbol(ev.yahoo_symbol or ev.symbol, ev.market or "JP")
    # 旧 RFC822 などの published_at を YYYY-MM-DD に正規化 (None なら detected_at にフォールバック)
    pub = _normalize_date(ev.published_at or "")
    if not pub and ev.detected_at:
        try:
            pub = ev.detected_at.date().isoformat()
        except Exception:
            pub = None
    if not pub:
        return None
    rows = _load_history(sym)
    if not rows or len(rows) < 5:
        return None
    idx0 = _find_index_at_or_after(rows, pub)
    if idx0 is None or idx0 >= len(rows):
        return None
    event_close = rows[idx0].get("close")
    if not event_close or event_close <= 0:
        return None

    def at(off: int) -> Optional[float]:
        j = idx0 + off
        if 0 <= j < len(rows):
            return rows[j].get("close")
        return None

    t1 = at(1); t3 = at(3); t5 = at(5); t10 = at(10); t20 = at(20)

    # 20営業日のmax/drawdown と hit_20
    window = rows[idx0 + 1: idx0 + 21]
    if len(window) < 5:
        # 観測期間が短い (まだ20営業日経っていない)
        return {
            "insufficient_data": True,
            "event_close": event_close,
            "t1_close": t1, "t3_close": t3, "t5_close": t5,
            "t10_close": t10, "t20_close": t20,
        }
    max_gain = 0.0
    max_dd = 0.0
    hit_20 = False
    hit_10 = False
    days_to_hit_20 = None
    for k, r in enumerate(window, start=1):
        hi = r.get("high") or r.get("close") or 0
        lo = r.get("low") or r.get("close") or 0
        g_hi = (hi - event_close) / event_close * 100.0
        g_lo = (lo - event_close) / event_close * 100.0
        if g_hi > max_gain:
            max_gain = g_hi
        if g_lo < max_dd:
            max_dd = g_lo
        if not hit_10 and g_hi >= 10.0:
            hit_10 = True
        if not hit_20 and g_hi >= 20.0:
            hit_20 = True
            days_to_hit_20 = k

    return {
        "insufficient_data": False,
        "event_close": event_close,
        "t1_close": t1, "t3_close": t3, "t5_close": t5,
        "t10_close": t10, "t20_close": t20,
        "gain_1d": round((t1 - event_close) / event_close * 100.0, 3) if t1 else None,
        "gain_5d": round((t5 - event_close) / event_close * 100.0, 3) if t5 else None,
        "gain_20d": round((t20 - event_close) / event_close * 100.0, 3) if t20 else None,
        "max_gain_20d": round(max_gain, 3),
        "max_drawdown_20d": round(max_dd, 3),
        "hit_10_percent_within_20d": hit_10,
        "hit_20_percent_within_20d": hit_20,
        "days_to_hit_20": days_to_hit_20,
    }


def compute_material_outcomes(lookback_days: int = 60, max_events: int = 500) -> Dict:
    """直近 lookback_days の MaterialEvent について outcome を計算・保存 (idempotent)。

    historical_ohlcv が無い銘柄はスキップ。すでに MaterialOutcome がある event は再計算で上書き。
    """
    db: Session = SessionLocal()
    try:
        # detected_at で粗くフィルタ (published_at のフォーマット差異に依らない)
        cutoff_dt = date.today() - timedelta(days=lookback_days)
        events = (db.query(MaterialEvent)
                  .filter(MaterialEvent.detected_at >= cutoff_dt)
                  .order_by(MaterialEvent.detected_at.desc())
                  .limit(max_events).all())
    finally:
        db.close()

    processed = 0
    saved = 0
    updated = 0
    skipped_no_data = 0
    insufficient = 0
    hit_20_count = 0
    hit_10_count = 0
    sample_failures = []  # symbol別失敗理由のサンプル

    for ev in events:
        try:
            result = compute_outcome_for_event(ev)
        except Exception as e:
            logger.warning(f"outcome compute failed eid={ev.id}: {e}")
            continue
        processed += 1
        if result is None:
            skipped_no_data += 1
            if len(sample_failures) < 5:
                sample_failures.append({"event_id": ev.id, "symbol": ev.symbol,
                                        "yahoo_symbol": ev.yahoo_symbol,
                                        "published_at": (ev.published_at or "")[:25]})
            continue
        if result.get("insufficient_data"):
            insufficient += 1
        if result.get("hit_20_percent_within_20d"):
            hit_20_count += 1
        if result.get("hit_10_percent_within_20d"):
            hit_10_count += 1

        db = SessionLocal()
        try:
            existing = (db.query(MaterialOutcome)
                        .filter(MaterialOutcome.material_event_id == ev.id)
                        .first())
            base = {
                "material_event_id": ev.id,
                "symbol": ev.symbol,
                "market": ev.market,
                "catalyst_category": ev.catalyst_category,
                "source_type": ev.source_type,
                "source_rank": ev.source_rank,
                "published_at": (_normalize_date(ev.published_at or "")
                                 or (ev.detected_at.date().isoformat() if ev.detected_at else None)),
            }
            payload = {**base, **{k: v for k, v in result.items()
                                  if k in ("event_close", "t1_close", "t3_close",
                                           "t5_close", "t10_close", "t20_close",
                                           "gain_1d", "gain_5d", "gain_20d",
                                           "max_gain_20d", "max_drawdown_20d",
                                           "hit_10_percent_within_20d",
                                           "hit_20_percent_within_20d",
                                           "days_to_hit_20", "insufficient_data")}}
            if existing:
                for k, v in payload.items():
                    setattr(existing, k, v)
                updated += 1
            else:
                db.add(MaterialOutcome(**payload))
                saved += 1
            db.commit()
        except Exception as e:
            db.rollback()
            logger.warning(f"outcome save failed eid={ev.id}: {e}")
        finally:
            db.close()

    return {
        "status": "ok",
        "processed": processed,
        "saved_new": saved,
        "updated": updated,
        "skipped_no_ohlcv": skipped_no_data,
        "insufficient_window": insufficient,
        "hit_20_count": hit_20_count,
        "hit_10_count": hit_10_count,
        "events_examined": len(events),
        "sample_failures": sample_failures,
    }


def get_category_performance(min_samples: int = 3) -> Dict:
    """カテゴリ × ソース別の hit_20 率 / 平均gain / サンプル数 を集計。
    AI に「どの種類の材料が本当に効くか」を empirical に教える。"""
    db: Session = SessionLocal()
    try:
        # MaterialOutcome から有効データ (insufficient_data=False) を集計
        rows = (db.query(
            MaterialOutcome.catalyst_category,
            MaterialOutcome.source_type,
            _f.count(MaterialOutcome.id),
            _f.sum(_f.coalesce(MaterialOutcome.hit_20_percent_within_20d.cast(__import__("sqlalchemy").Integer), 0)),
            _f.sum(_f.coalesce(MaterialOutcome.hit_10_percent_within_20d.cast(__import__("sqlalchemy").Integer), 0)),
            _f.avg(MaterialOutcome.max_gain_20d),
            _f.avg(MaterialOutcome.max_drawdown_20d),
            _f.avg(MaterialOutcome.gain_5d),
        ).filter(MaterialOutcome.insufficient_data == False)
                .group_by(MaterialOutcome.catalyst_category, MaterialOutcome.source_type)
                .all())
    finally:
        db.close()

    items = []
    for cat, src, n, h20, h10, avg_max, avg_dd, avg_g5 in rows:
        if (n or 0) < min_samples:
            continue
        items.append({
            "catalyst_category": cat,
            "source_type": src,
            "sample_size": int(n or 0),
            "hit_20_rate": round((h20 or 0) / (n or 1), 3),
            "hit_10_rate": round((h10 or 0) / (n or 1), 3),
            "avg_max_gain_20d": round(float(avg_max or 0), 2),
            "avg_max_drawdown_20d": round(float(avg_dd or 0), 2),
            "avg_gain_5d": round(float(avg_g5 or 0), 2) if avg_g5 is not None else None,
        })
    items.sort(key=lambda x: -x["hit_20_rate"])
    return {"items": items, "count": len(items)}


def get_source_effectiveness(min_samples: int = 5) -> Dict:
    """source_type 単体の予測力サマリ (どのニュース源が surge につながりやすいか)"""
    db: Session = SessionLocal()
    try:
        from sqlalchemy import Integer as _Int
        rows = (db.query(
            MaterialOutcome.source_type,
            _f.count(MaterialOutcome.id),
            _f.sum(MaterialOutcome.hit_20_percent_within_20d.cast(_Int)),
            _f.avg(MaterialOutcome.max_gain_20d),
        ).filter(MaterialOutcome.insufficient_data == False)
                .group_by(MaterialOutcome.source_type).all())
    finally:
        db.close()
    items = [{
        "source_type": st, "sample_size": int(n or 0),
        "hit_20_rate": round((h20 or 0) / (n or 1), 3),
        "avg_max_gain_20d": round(float(avg or 0), 2),
    } for st, n, h20, avg in rows if (n or 0) >= min_samples]
    items.sort(key=lambda x: -x["hit_20_rate"])
    return {"items": items, "count": len(items)}
