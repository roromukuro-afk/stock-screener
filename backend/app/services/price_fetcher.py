"""株価データ取得サービス (yfinance + サンプルフォールバック)"""
import os
import pandas as pd
import numpy as np
from typing import Dict, Optional, Tuple
from datetime import datetime
import requests

from app.services.sample_data import generate_sample_price_data, generate_sample_info

_fx_cache: Dict[str, Tuple[float, datetime]] = {}
_use_sample = False


def set_sample_mode(enabled: bool):
    global _use_sample
    _use_sample = enabled


def is_sample_mode() -> bool:
    if os.getenv("SAMPLE_MODE", "false").lower() == "true":
        return True
    return _use_sample


def get_usd_jpy() -> float:
    default_fx = float(os.getenv("DEFAULT_USDJPY", "155"))
    if is_sample_mode():
        return default_fx
    cached = _fx_cache.get("USDJPY")
    if cached and (datetime.now() - cached[1]).seconds < 3600:
        return cached[0]
    try:
        # yfinanceの代わりに直接Yahoo Finance APIを叩く(より安定)
        url = "https://query1.finance.yahoo.com/v8/finance/chart/USDJPY=X?interval=1d&range=5d"
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code == 200:
            data = r.json()
            result = data.get("chart", {}).get("result", [])
            if result:
                meta = result[0].get("meta", {})
                rate = meta.get("regularMarketPrice")
                if rate:
                    _fx_cache["USDJPY"] = (float(rate), datetime.now())
                    return float(rate)
    except Exception as e:
        print(f"FX fetch failed: {e}")
    return default_fx


def _fetch_from_yahoo_api(symbol: str, period: str = "3mo") -> Optional[pd.DataFrame]:
    """直接Yahoo Finance Chart APIを叩く(yfinanceに依存しない)"""
    range_map = {"1mo": "1mo", "3mo": "3mo", "6mo": "6mo", "1y": "1y", "2y": "2y", "5y": "5y", "10y": "10y", "max": "max"}
    yf_range = range_map.get(period, "3mo")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": yf_range}
    try:
        r = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        result = data.get("chart", {}).get("result", [])
        if not result:
            return None
        chart = result[0]
        timestamps = chart.get("timestamp", [])
        indicators = chart.get("indicators", {})
        quote = indicators.get("quote", [{}])[0]

        opens = quote.get("open", [])
        highs = quote.get("high", [])
        lows = quote.get("low", [])
        closes = quote.get("close", [])
        volumes = quote.get("volume", [])

        if not closes or len(closes) < 5:
            return None

        # None値を前の値で埋める
        def fill_none(arr):
            last = None
            result = []
            for v in arr:
                if v is None:
                    result.append(last if last is not None else 0.0)
                else:
                    last = v
                    result.append(v)
            return result

        opens = fill_none(opens)
        highs = fill_none(highs)
        lows = fill_none(lows)
        closes = fill_none(closes)
        volumes = [v if v is not None else 0 for v in volumes]

        dates = [datetime.fromtimestamp(t).strftime("%Y-%m-%d") for t in timestamps]

        df = pd.DataFrame({
            "date": dates,
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": volumes,
        })
        df = df[df["close"] > 0]
        return df if len(df) >= 5 else None
    except Exception as e:
        print(f"Yahoo API fetch failed for {symbol}: {e}")
        return None


def _fetch_quote_meta_from_yahoo(symbol: str) -> Dict:
    """Yahoo Finance API から最新クォートのメタ情報を取得"""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": "5d"}
    try:
        r = requests.get(url, params=params, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if r.status_code != 200:
            return {}
        data = r.json()
        result = (data.get("chart") or {}).get("result") or []
        if not result:
            return {}
        chart = result[0]
        meta = chart.get("meta", {}) or {}
        return {
            "regularMarketPrice": meta.get("regularMarketPrice"),
            "regularMarketTime": meta.get("regularMarketTime"),  # epoch
            "previousClose": meta.get("previousClose"),
            "marketState": meta.get("marketState"),
            "exchangeTimezoneName": meta.get("exchangeTimezoneName"),
            "currency": meta.get("currency"),
            "instrumentType": meta.get("instrumentType"),
        }
    except Exception:
        return {}


def get_stock_quote_with_freshness(symbol: str, market: str = None) -> Dict:
    """価格 + 鮮度情報を返す。
    Returns: {price, quote_date, quote_timestamp, freshness_status, is_stale, stale_reason, ...}
    """
    from app.services.freshness import assess_freshness
    if market is None:
        market = "JP" if ".T" in symbol else "US"

    if is_sample_mode():
        # サンプルモード: 当日扱い
        df = generate_sample_price_data(symbol, market=market)
        if df is None or df.empty:
            return {
                "price": None,
                "quote_date": None,
                "quote_timestamp": None,
                **assess_freshness(market, None, None, "sample"),
                "data_source": "sample",
            }
        last = df.iloc[-1]
        return {
            "price": float(last["close"]),
            "quote_date": str(last["date"]),
            "quote_timestamp": None,
            **assess_freshness(market, str(last["date"]), None, "sample"),
            "data_source": "sample",
        }

    # 実データ: meta + history で照合
    meta = _fetch_quote_meta_from_yahoo(symbol)
    df = _fetch_from_yahoo_api(symbol, period="5d")

    price = None
    quote_date = None
    quote_ts = None

    if meta.get("regularMarketPrice"):
        price = float(meta["regularMarketPrice"])
    if meta.get("regularMarketTime"):
        quote_ts = float(meta["regularMarketTime"])
        try:
            quote_date = datetime.fromtimestamp(quote_ts).date().isoformat()
        except Exception:
            quote_date = None

    # historyの最終日とprice/dateを照合・補完
    if df is not None and len(df) >= 1:
        last_row = df.iloc[-1]
        last_date = str(last_row.get("date"))
        last_close = float(last_row.get("close"))
        if not quote_date:
            quote_date = last_date
        if price is None:
            price = last_close
        # quote_dateとhistoryの最終日がズレる場合はhistoryを優先(より保守的)
        if quote_date and last_date and quote_date < last_date:
            quote_date = last_date

    return {
        "price": price,
        "quote_date": quote_date,
        "quote_timestamp": quote_ts,
        **assess_freshness(market, quote_date, quote_ts, "yfinance"),
        "data_source": "yfinance",
    }


def get_stock_data(symbol: str, period: str = "3mo", market: str = None) -> Optional[pd.DataFrame]:
    """株価データを取得。サンプルモードまたはyfinance失敗時は合成データを返す。"""
    if is_sample_mode():
        return generate_sample_price_data(symbol, market=market)

    # 直接Yahoo Finance APIを叩く
    df = _fetch_from_yahoo_api(symbol, period)
    if df is not None and len(df) >= 5:
        return df

    # フォールバック: yfinanceを試す
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        if not hist.empty and len(hist) >= 5:
            hist = hist.reset_index()
            hist.columns = [c.lower() for c in hist.columns]
            if "date" in hist.columns:
                hist["date"] = pd.to_datetime(hist["date"]).dt.strftime("%Y-%m-%d")
            return hist
    except Exception as e:
        print(f"yfinance failed for {symbol}: {e}")

    return None


def get_stock_info(symbol: str, market: str = None) -> Dict:
    if is_sample_mode():
        return generate_sample_info(symbol, market=market)
    try:
        import yfinance as yf
        ticker = yf.Ticker(symbol)
        info = ticker.info or {}
        return {
            "name": info.get("longName") or info.get("shortName") or symbol,
            "sector": info.get("sector", ""),
            "industry": info.get("industry", ""),
            "market_cap": info.get("marketCap", 0),
            "currency": info.get("currency", "JPY" if ".T" in symbol else "USD"),
            "country": info.get("country", ""),
        }
    except Exception:
        return generate_sample_info(symbol, market=market)
