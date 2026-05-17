"""価格データ鮮度サービス

価格データの取得時刻、対象取引日、市場時間との関係を判定し、
取引時間中に古いデータを使わないようゲートを実装する。
"""
from datetime import datetime, timezone, timedelta, time
from typing import Dict, Optional, Tuple
from zoneinfo import ZoneInfo


JST = ZoneInfo("Asia/Tokyo")
EST = ZoneInfo("America/New_York")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def market_open_for(market: str, now: Optional[datetime] = None) -> Tuple[bool, str, datetime]:
    """指定市場が今 取引時間内か返す。(open?, market_tz_name, market_now)"""
    if now is None:
        now = now_utc()

    if market == "JP":
        tz = JST
        local = now.astimezone(tz)
        # JST 09:00-11:30 / 12:30-15:30 (前後場)、土日除外
        if local.weekday() >= 5:
            return False, "Asia/Tokyo", local
        morning = (time(9, 0) <= local.time() < time(11, 30))
        afternoon = (time(12, 30) <= local.time() < time(15, 30))
        return (morning or afternoon), "Asia/Tokyo", local
    else:
        tz = EST
        local = now.astimezone(tz)
        if local.weekday() >= 5:
            return False, "America/New_York", local
        # NYSE/NASDAQ: 09:30-16:00 ET
        return (time(9, 30) <= local.time() < time(16, 0)), "America/New_York", local


def _trading_day_for(market: str, now_local: datetime) -> str:
    """その市場の現在の取引日(YYYY-MM-DD)。市場休場日は直近営業日に遡る"""
    d = now_local.date()
    # 土日対応
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    return d.isoformat()


def _previous_trading_day(market: str, now_local: datetime) -> str:
    d = now_local.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d = d - timedelta(days=1)
    return d.isoformat()


def assess_freshness(
    market: str,
    quote_date: Optional[str],          # YYYY-MM-DD - the trading date of the price
    quote_timestamp: Optional[float],   # epoch seconds - exact time of last quote (if available)
    data_source: str = "yfinance",
    now: Optional[datetime] = None,
) -> Dict:
    """価格データの鮮度判定

    Returns a dict with keys:
        freshness_status, is_stale, stale_reason, delay_minutes_estimated,
        is_realtime_or_delayed, is_market_open_at_fetch,
        exchange_timezone, fetched_at_utc, fetched_at_jst, latest_trading_day
    """
    if now is None:
        now = now_utc()

    is_open, tz_name, market_now = market_open_for(market, now)
    today_trading = _trading_day_for(market, market_now)
    prev_trading = _previous_trading_day(market, market_now)

    fetched_at_utc_str = now.isoformat()
    fetched_at_jst_str = now.astimezone(JST).isoformat()

    base = {
        "fetched_at_utc": fetched_at_utc_str,
        "fetched_at_jst": fetched_at_jst_str,
        "exchange_timezone": tz_name,
        "is_market_open_at_fetch": is_open,
        "latest_trading_day": today_trading,
        "delay_minutes_estimated": None,
        "is_realtime_or_delayed": "unknown",
    }

    # 価格対象日が不明
    if not quote_date:
        return {
            **base,
            "freshness_status": "unknown_timestamp",
            "is_stale": True,
            "stale_reason": "quote_date_unknown",
        }

    # quote_timestamp があれば遅延を分単位で計算
    delay_minutes = None
    if quote_timestamp:
        try:
            quote_dt = datetime.fromtimestamp(float(quote_timestamp), tz=timezone.utc)
            delay_minutes = max(0, (now - quote_dt).total_seconds() / 60.0)
        except (ValueError, TypeError, OSError):
            delay_minutes = None
    base["delay_minutes_estimated"] = round(delay_minutes, 1) if delay_minutes is not None else None

    # 鮮度判定
    if quote_date == today_trading:
        # 当日のデータ
        if is_open:
            if delay_minutes is None:
                # timestamp 不明だが当日データ
                return {
                    **base,
                    "freshness_status": "fresh_delayed_within_20min",
                    "is_stale": False,
                    "stale_reason": None,
                    "is_realtime_or_delayed": "delayed",
                }
            if delay_minutes <= 1:
                return {**base, "freshness_status": "fresh_realtime", "is_stale": False, "stale_reason": None, "is_realtime_or_delayed": "realtime"}
            if delay_minutes <= 20:
                return {**base, "freshness_status": "fresh_delayed_within_20min", "is_stale": False, "stale_reason": None, "is_realtime_or_delayed": "delayed"}
            # 当日データだが20分以上古い → ペナルティ
            return {
                **base,
                "freshness_status": "stale_intraday_over_20min",
                "is_stale": True,
                "stale_reason": f"quote {delay_minutes:.0f}min old during market hours",
                "is_realtime_or_delayed": "delayed",
            }
        else:
            # 取引時間外で当日データ → 大引け後の終値
            return {**base, "freshness_status": "fresh_latest_close_after_market", "is_stale": False, "stale_reason": None, "is_realtime_or_delayed": "close"}

    elif quote_date == prev_trading:
        # 前営業日データ
        if is_open:
            # 取引時間中に前営業日データしか無い → 除外
            return {
                **base,
                "freshness_status": "stale_previous_day_during_market",
                "is_stale": True,
                "stale_reason": "previous trading day quote during market hours",
                "is_realtime_or_delayed": "close",
            }
        else:
            # 場閉まってる/休場 → 直近営業日の終値として許容
            return {**base, "freshness_status": "fresh_latest_close_after_market", "is_stale": False, "stale_reason": None, "is_realtime_or_delayed": "close"}
    else:
        # 2営業日以上前
        return {
            **base,
            "freshness_status": "stale_over_1day",
            "is_stale": True,
            "stale_reason": f"quote_date={quote_date} is older than latest trading day {today_trading}",
            "is_realtime_or_delayed": "close",
        }
