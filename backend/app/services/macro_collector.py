"""マクロ指標 (USD/JPY, Nikkei225, TOPIX, VIX, 10yr 等) を Yahoo Finance から日次取得し
MacroIndicator テーブルに保存。リスクオン/オフ判定 や 為替感応度計算の入力。

これは投資助言ではありません。分析・学習・検証目的のデータ収集です。
"""
from typing import Dict, List, Optional
from datetime import date, timedelta
import logging

from app.database import SessionLocal
from app.models.models import MacroIndicator

logger = logging.getLogger(__name__)

# (indicator_code, yahoo_symbol, display_name)
MACRO_TICKERS = [
    ("USDJPY", "JPY=X", "USD/JPY 為替"),
    ("NIKKEI225", "^N225", "日経平均株価"),
    ("TOPIX", "^TPX", "TOPIX"),
    ("MOTHERS", "1563.T", "東証マザーズ ETF"),  # 代替
    ("VIX", "^VIX", "VIX 恐怖指数"),
    ("TNX", "^TNX", "米10年金利"),
    ("SOX", "^SOX", "SOX 半導体指数"),
    ("SP500", "^GSPC", "S&P500"),
    ("NDX", "^NDX", "NASDAQ100"),
    ("DXY", "DX-Y.NYB", "ドルインデックス"),
    ("WTI", "CL=F", "WTI原油"),
    ("GOLD", "GC=F", "金"),
]


def fetch_macro_yahoo(yahoo_symbol: str, period: str = "3mo") -> Optional[List[Dict]]:
    """Yahoo Finance から指標OHLCVを取得 (price_fetcher を再利用)"""
    try:
        from app.services.price_fetcher import get_stock_data
        df = get_stock_data(yahoo_symbol, period=period)
        if df is None or len(df) < 5:
            return None
        df = df.sort_values("date").reset_index(drop=True)
        rows = df.to_dict(orient="records")
        return rows
    except Exception as e:
        logger.warning(f"macro fetch {yahoo_symbol} failed: {e}")
        return None


def _percent_change(rows: List[Dict], idx: int, lookback: int) -> Optional[float]:
    if idx - lookback < 0 or idx >= len(rows):
        return None
    prev = rows[idx - lookback].get("close")
    cur = rows[idx].get("close")
    if not prev or prev == 0 or not cur:
        return None
    return round((cur - prev) / prev * 100.0, 3)


def collect_macro_indicators(period: str = "3mo") -> Dict:
    """全マクロ指標を Yahoo Finance から取得し、MacroIndicator に保存 (idempotent)"""
    total_fetched = 0
    saved = 0
    updated = 0
    failed = 0
    by_code = {}

    for code, ysym, name in MACRO_TICKERS:
        try:
            rows = fetch_macro_yahoo(ysym, period=period)
            if not rows:
                failed += 1
                by_code[code] = {"fetched": 0, "status": "fetch_failed"}
                continue
            total_fetched += len(rows)
            n_saved = 0
            n_updated = 0
            for i, r in enumerate(rows):
                d_str = str(r.get("date") or "")[:10]
                if not d_str:
                    continue
                close = r.get("close")
                if close is None:
                    continue
                ch1 = _percent_change(rows, i, 1)
                ch5 = _percent_change(rows, i, 5)
                ch20 = _percent_change(rows, i, 20)
                db = SessionLocal()
                try:
                    existing = (db.query(MacroIndicator)
                                .filter(MacroIndicator.indicator_code == code)
                                .filter(MacroIndicator.date == d_str)
                                .first())
                    payload = {
                        "indicator_code": code, "indicator_name": name,
                        "date": d_str,
                        "close": float(close),
                        "open": float(r.get("open") or 0) or None,
                        "high": float(r.get("high") or 0) or None,
                        "low": float(r.get("low") or 0) or None,
                        "volume": float(r.get("volume") or 0) or None,
                        "change_1d_percent": ch1,
                        "change_5d_percent": ch5,
                        "change_20d_percent": ch20,
                    }
                    if existing:
                        for k, v in payload.items():
                            setattr(existing, k, v)
                        n_updated += 1
                    else:
                        db.add(MacroIndicator(**payload))
                        n_saved += 1
                    db.commit()
                except Exception:
                    db.rollback()
                finally:
                    db.close()
            saved += n_saved
            updated += n_updated
            by_code[code] = {"fetched": len(rows), "saved_new": n_saved, "updated": n_updated}
        except Exception as e:
            failed += 1
            by_code[code] = {"status": "failed", "error": str(e)[:200]}

    return {
        "status": "ok", "total_fetched": total_fetched,
        "saved_new": saved, "updated": updated, "failed": failed,
        "by_code": by_code,
    }


def get_latest_snapshot() -> Dict:
    """各 indicator の最新値・各期間変動率を返す (Web表示用)"""
    db = SessionLocal()
    try:
        out = {}
        for code, ysym, name in MACRO_TICKERS:
            last = (db.query(MacroIndicator)
                    .filter(MacroIndicator.indicator_code == code)
                    .order_by(MacroIndicator.date.desc())
                    .first())
            if last:
                out[code] = {
                    "name": last.indicator_name, "date": last.date,
                    "close": last.close,
                    "change_1d_percent": last.change_1d_percent,
                    "change_5d_percent": last.change_5d_percent,
                    "change_20d_percent": last.change_20d_percent,
                }
        # 簡易リスクオン/オフ判定
        risk = "neutral"
        vix = out.get("VIX", {}).get("close")
        n225_ch5 = out.get("NIKKEI225", {}).get("change_5d_percent")
        if vix is not None and n225_ch5 is not None:
            if vix > 25 or n225_ch5 < -5:
                risk = "risk_off"
            elif vix < 18 and n225_ch5 > 2:
                risk = "risk_on"
        return {"indicators": out, "risk_regime": risk}
    finally:
        db.close()
