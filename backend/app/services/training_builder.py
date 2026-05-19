"""過去5年教師データ構築エンジン

急騰銘柄だけを集めず、negative case (急騰前夜似なのに不発 / 上がり切り失敗 /
材料弱い失敗 / 悪材料失敗 / 材料出尽くし失敗) も生成する。
T0以降のデータは label にだけ使い、T-1特徴量には混ぜない。
"""
import threading
import math
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models.models import (
    HistoricalOHLCV, SurgeEvent, TrainingWindow,
    TrainingFeatureVector, TrainingBuildJob, TrainingDataQualityReport,
)
from app.services import universe_db
from app.services.price_fetcher import get_stock_data


# ===== known surge seed (過去に+20%以上急騰実績がある銘柄) =====
KNOWN_SURGE_SEED_JP = [
    "3936.T", "9256.T", "1434.T", "6613.T", "4316.T", "4422.T", "4582.T",
    "5343.T", "6740.T", "8105.T", "9610.T", "3905.T", "485A.T", "2693.T",
    "6480.T", "7162.T", "1436.T", "7256.T", "8137.T", "4368.T", "6141.T",
    "2180.T", "4392.T", "2901.T", "4840.T", "3810.T", "6666.T",
]
KNOWN_SURGE_SEED_US = [
    "AEHL", "SNAL", "AIFF", "AKAN", "ARTL", "ASNS", "ATER", "CNSP", "DRCT",
    "INOD", "BWEN", "OSS", "KULR", "SKLZ", "PRSO", "PFSA", "TDIC", "TPET",
    "EVC", "RXT", "BAND", "WEST", "CLNN", "AVTX", "ERNA", "MEI", "FNGR",
    "EZGO", "OCG", "ABVE",
]


def get_seed_symbols(market: str = "BOTH") -> List[Dict]:
    """known_surge_seedをuniverse形式で返す"""
    result = []
    if market in ("JP", "BOTH"):
        for s in KNOWN_SURGE_SEED_JP:
            result.append({"symbol": s, "yahoo_symbol": s, "name": s, "market": "JP"})
    if market in ("US", "BOTH"):
        for s in KNOWN_SURGE_SEED_US:
            result.append({"symbol": s, "yahoo_symbol": s, "name": s, "market": "US"})
    return result


def select_target_universe(target_mode: str, markets: List[str], max_symbols: int, include_adr: bool) -> List[Dict]:
    """target_modeに応じてuniverseを選定"""
    from app.services import universe_db
    from app.database import SessionLocal
    from app.models.models import UniverseSymbol
    from sqlalchemy import asc

    if target_mode == "known_surge_seed":
        m = "BOTH" if (len(markets) > 1 or "JP" in markets and "US" in markets) else markets[0] if markets else "BOTH"
        seed = get_seed_symbols(m)
        return seed[:max_symbols] if max_symbols > 0 else seed

    if target_mode in ("low_price_only", "jp_low_price_priority", "us_low_price_priority"):
        # 低位株: priceは持ってないので yahoo_symbol 末尾4桁数値が小さい(JP)などのヒューリスティック不可
        # eligible全件取得→max_symbolsまで
        return universe_db.list_eligible_yahoo_symbols(markets=markets, max_count=max_symbols, include_adr=include_adr)

    if target_mode == "small_cap_priority":
        # 小型株優先: nasdaqlisted小型は通常後ろの方の銘柄。eligibleの後半を取る
        all_syms = universe_db.list_eligible_yahoo_symbols(markets=markets, max_count=0, include_adr=include_adr)
        # ランダムシャッフルで小型側を含める
        import random
        random.seed(42)
        random.shuffle(all_syms)
        return all_syms[:max_symbols] if max_symbols > 0 else all_syms

    if target_mode in ("us_small_cap_priority", "high_volatility_priority"):
        all_syms = universe_db.list_eligible_yahoo_symbols(markets=["US"], max_count=0, include_adr=include_adr)
        # USの3-5文字ティッカーは小型株が多い
        small = [s for s in all_syms if len(s.get("symbol", "")) <= 4]
        import random
        random.seed(42)
        random.shuffle(small)
        return small[:max_symbols] if max_symbols > 0 else small

    if target_mode == "adr_priority":
        from app.database import SessionLocal
        from app.models.models import UniverseSymbol
        db = SessionLocal()
        try:
            rows = db.query(UniverseSymbol).filter(
                UniverseSymbol.is_adr == True,
                UniverseSymbol.is_screening_eligible == True,
            ).limit(max_symbols if max_symbols > 0 else 1000).all()
            return [{"symbol": r.symbol, "yahoo_symbol": r.yahoo_symbol or r.symbol,
                     "name": r.name, "market": r.market} for r in rows]
        finally:
            db.close()

    if target_mode == "random_sample":
        all_syms = universe_db.list_eligible_yahoo_symbols(markets=markets, max_count=0, include_adr=include_adr)
        import random
        random.shuffle(all_syms)
        return all_syms[:max_symbols] if max_symbols > 0 else all_syms

    # default = "all"
    return universe_db.list_eligible_yahoo_symbols(markets=markets, max_count=max_symbols, include_adr=include_adr)


_progress: Dict = {
    "running": False, "status": "idle", "phase": "",
    "current_symbol": "", "processed_symbols": 0, "total_symbols": 0,
    "fetched_rows": 0, "surge_events_found": 0,
    "negative_cases_found": 0, "feature_vectors_created": 0,
    "error_count": 0, "job_id": None,
}
_lock = threading.Lock()


def get_progress() -> Dict:
    with _lock:
        return dict(_progress)


def _set(**kwargs):
    with _lock:
        _progress.update(kwargs)


# =============== 過去OHLCV取得 ===============
def _fetch_history_for_symbol(symbol: str, market: str, period: str = "5y") -> int:
    """1銘柄分の5年OHLCVを取得しDBに保存。挿入件数を返す"""
    df = get_stock_data(symbol, period=period, market=market)
    if df is None or len(df) < 30:
        return 0
    df = df.sort_values("date").reset_index(drop=True)

    db: Session = SessionLocal()
    try:
        existing_dates = {
            r[0] for r in db.query(HistoricalOHLCV.date)
            .filter(HistoricalOHLCV.symbol == symbol).all()
        }
        rows_to_insert = []
        for _, row in df.iterrows():
            d = str(row["date"])
            if d in existing_dates:
                continue
            close = float(row["close"]) if row["close"] is not None else None
            if close is None or close <= 0 or math.isnan(close):
                continue
            rows_to_insert.append(HistoricalOHLCV(
                symbol=symbol,
                yahoo_symbol=symbol,
                market=market,
                date=d,
                open=_clean_float(row.get("open")),
                high=_clean_float(row.get("high")),
                low=_clean_float(row.get("low")),
                close=close,
                adjusted_close=close,  # yfinance default returns adjusted
                volume=_clean_float(row.get("volume")),
                data_source="yfinance",
                is_adjusted=True,
            ))
        if rows_to_insert:
            db.add_all(rows_to_insert)
            db.commit()
        return len(rows_to_insert)
    finally:
        db.close()


def _clean_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _clean_int(v) -> Optional[int]:
    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return int(f)
    except (TypeError, ValueError):
        return None


def _clean_str(v) -> Optional[str]:
    if v is None:
        return None
    try:
        s = str(v).strip()
        if not s or s.lower() == "nan":
            return None
        # pandas.Timestamp -> "YYYY-MM-DD" 形式に正規化
        if len(s) > 10 and s[10] == " ":
            s = s[:10]
        return s
    except Exception:
        return None


def _clean_bool(v) -> bool:
    if v is None:
        return False
    try:
        if isinstance(v, bool):
            return v
        return bool(v)
    except Exception:
        return False


def _sanitize_event_dict(e: Dict) -> Dict:
    """surge_event 用に全フィールドを Python 標準型に変換 (PostgreSQL安全)"""
    return {
        "symbol": _clean_str(e.get("symbol")),
        "yahoo_symbol": _clean_str(e.get("yahoo_symbol") or e.get("symbol")),
        "name": _clean_str(e.get("name")),
        "market": _clean_str(e.get("market")),
        "event_date": _clean_str(e.get("event_date")),
        "move_percent": _clean_float(e.get("move_percent")),
        "threshold_type": _clean_str(e.get("threshold_type")),
        "close_t_minus_1": _clean_float(e.get("close_t_minus_1")),
        "close_t0": _clean_float(e.get("close_t0")),
        "volume_t0": _clean_float(e.get("volume_t0")),
        "volume_ratio_t0": _clean_float(e.get("volume_ratio_t0")),
        "source": _clean_str(e.get("source")) or "training_builder",
        "is_valid": _clean_bool(e.get("is_valid")),
        "validation_warning": _clean_str(e.get("validation_warning")),
    }


def _sanitize_feature_dict(f: Dict) -> Dict:
    """training_feature_vector用sanitize"""
    out = {}
    bool_keys = {
        "high_close_flag", "low_close_flag", "range_break_flag", "squeeze_flag",
        "prior_big_volume_flag", "selling_exhaustion_flag", "reaccumulation_flag",
        "pre_breakout_flag", "material_known_flag", "bad_news_flag",
        "dilution_risk_flag", "label_hit_20_percent",
    }
    str_keys = {"candle_state", "catalyst_category", "label_success_class"}
    for k, v in f.items():
        if k in bool_keys:
            out[k] = _clean_bool(v)
        elif k in str_keys:
            out[k] = _clean_str(v)
        else:
            out[k] = _clean_float(v)
    return out


def _list_history_for_symbol(symbol: str) -> Optional[pd.DataFrame]:
    db: Session = SessionLocal()
    try:
        rows = (db.query(HistoricalOHLCV)
                .filter(HistoricalOHLCV.symbol == symbol)
                .order_by(HistoricalOHLCV.date).all())
        if not rows:
            return None
        return pd.DataFrame([{
            "date": r.date, "open": r.open, "high": r.high,
            "low": r.low, "close": r.close, "volume": r.volume,
        } for r in rows])
    finally:
        db.close()


# =============== 急騰イベント検出 ===============
def _detect_surge_events_for_symbol(symbol: str, market: str,
                                    surge_threshold: float = 20.0,
                                    semi_threshold: float = 15.0) -> List[Dict]:
    df = _list_history_for_symbol(symbol)
    if df is None or len(df) < 30:
        return []
    df = df.sort_values("date").reset_index(drop=True)
    closes = df["close"].astype(float).values
    volumes = df["volume"].astype(float).values

    events = []
    for i in range(1, len(closes)):
        prev_raw = closes[i - 1]
        curr_raw = closes[i]
        # NaN/inf を完全排除
        try:
            prev = float(prev_raw)
            curr = float(curr_raw)
        except (TypeError, ValueError):
            continue
        if math.isnan(prev) or math.isnan(curr) or math.isinf(prev) or math.isinf(curr):
            continue
        if prev <= 0 or curr <= 0:
            continue
        move = (curr - prev) / prev * 100
        if math.isnan(move) or math.isinf(move):
            continue
        # split検出: -50%急落 or +200%急騰 はwarning
        warning = None
        if move <= -45 or move >= 200:
            warning = f"極端な変動率 ({move:.1f}%): 株式分割/併合の可能性"
        # 出来高ゼロ近辺は弾く
        vol = float(volumes[i]) if not math.isnan(volumes[i]) else 0
        if vol < 100:
            continue

        threshold_type = None
        if move >= surge_threshold:
            threshold_type = "surge_20"
        elif move >= semi_threshold:
            threshold_type = "semi_surge_15"

        if threshold_type:
            # 出来高倍率
            vol_window = volumes[max(0, i - 20):i]
            vol_avg = float(np.nanmean(vol_window)) if len(vol_window) > 0 else None
            vol_ratio = (vol / vol_avg) if vol_avg and vol_avg > 0 else None

            events.append({
                "symbol": symbol,
                "market": market,
                "event_date": str(df.iloc[i]["date"]),
                "move_percent": round(move, 3),
                "threshold_type": threshold_type,
                "close_t_minus_1": float(prev),
                "close_t0": float(curr),
                "volume_t0": vol,
                "volume_ratio_t0": vol_ratio,
                "validation_warning": warning,
                "is_valid": warning is None,
            })
    return events


def _save_surge_events(events: List[Dict]) -> int:
    """surge_events を保存 — 全sanitize済み, per-row commit, エラーはautomation_errorsへ"""
    if not events:
        return 0
    from app.models.models import AutomationError  # noqa: F401
    saved = 0
    failed = 0
    for raw in events:
        e = _sanitize_event_dict(raw)
        # 必須フィールド検証 — 失敗もautomation_errorsへ
        if not e.get("symbol") or not e.get("event_date") or e.get("move_percent") is None:
            failed += 1
            try:
                err_db = SessionLocal()
                err_db.add(AutomationError(
                    job_id=None,
                    symbol=str(raw.get("symbol") or "?"),
                    market=str(raw.get("market") or "?"),
                    step="save_surge_event_validation",
                    error_type="ValidationError",
                    error_message=f"missing required field: symbol={e.get('symbol')} event_date={e.get('event_date')} move%={e.get('move_percent')}",
                    traceback=f"raw_event={str(raw)[:300]}",
                ))
                err_db.commit()
                err_db.close()
            except Exception:
                pass
            continue

        db: Session = SessionLocal()
        try:
            db.query(SurgeEvent).filter(
                SurgeEvent.symbol == e["symbol"],
                SurgeEvent.event_date == e["event_date"],
            ).delete()
            db.add(SurgeEvent(**e))
            db.commit()
            saved += 1
        except Exception as ex:
            db.rollback()
            failed += 1
            # automation_errors に記録
            try:
                err_db = SessionLocal()
                err_db.add(AutomationError(
                    job_id=None,
                    symbol=e.get("symbol"),
                    market=e.get("market"),
                    step="save_surge_event",
                    error_type=type(ex).__name__,
                    error_message=str(ex)[:500],
                    traceback=f"event_date={e.get('event_date')} threshold={e.get('threshold_type')} move%={e.get('move_percent')}",
                ))
                err_db.commit()
                err_db.close()
            except Exception:
                pass
        finally:
            db.close()
    return saved


# =============== T-1特徴量抽出 ===============
def _calc_t1_features(df: pd.DataFrame, t0_idx: int) -> Optional[Dict]:
    """T-1時点(t0_idx-1)で利用可能な情報だけで特徴量計算"""
    if t0_idx < 5 or t0_idx >= len(df):
        return None
    pre = df.iloc[: t0_idx].copy()  # T-1までだけ
    if len(pre) < 5:
        return None
    closes = pre["close"].astype(float).values
    highs = pre["high"].astype(float).values
    lows = pre["low"].astype(float).values
    opens = pre["open"].astype(float).values
    volumes = pre["volume"].astype(float).values

    def sma(arr, n):
        return float(np.mean(arr[-n:])) if len(arr) >= n else None

    c = float(closes[-1])
    o = float(opens[-1])
    h = float(highs[-1])
    l = float(lows[-1])
    v = float(volumes[-1])

    ma5 = sma(closes, 5)
    ma25 = sma(closes, 25)
    ma75 = sma(closes, 75)
    ma200 = sma(closes, 200)
    vol_avg5 = sma(volumes, 5)
    vol_avg20 = sma(volumes, 20)

    pc1 = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 and closes[-2] > 0 else 0
    pc3 = ((closes[-1] - closes[-4]) / closes[-4] * 100) if len(closes) >= 4 and closes[-4] > 0 else 0
    pc5 = ((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) >= 6 and closes[-6] > 0 else 0
    pc20 = ((closes[-1] - closes[-21]) / closes[-21] * 100) if len(closes) >= 21 and closes[-21] > 0 else 0

    vr5 = (v / vol_avg5) if vol_avg5 and vol_avg5 > 0 else None
    vr20 = (v / vol_avg20) if vol_avg20 and vol_avg20 > 0 else None

    ma25_dev = ((c - ma25) / ma25 * 100) if ma25 else 0

    rh20 = float(np.max(highs[-20:])) if len(highs) >= 20 else float(np.max(highs))
    rl20 = float(np.min(lows[-20:])) if len(lows) >= 20 else float(np.min(lows))
    rh60 = float(np.max(highs[-60:])) if len(highs) >= 60 else rh20

    resistance = rh20 if rh20 > c else rh60
    if resistance <= c:
        resistance = c * 1.10
    support = rl20 if rl20 < c else c * 0.92
    res_up = (resistance - c) / c * 100
    sup_dist = (c - support) / c * 100

    # ATR (period 14)
    atr = None
    if len(highs) >= 15:
        trs = []
        for i in range(-14, 0):
            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
            trs.append(tr)
        atr = float(np.mean(trs))

    # range_position
    if rh20 - rl20 > 0:
        range_pos = (c - rl20) / (rh20 - rl20)
    else:
        range_pos = 0.5

    # candle
    body = abs(c - o)
    rng = h - l if h > l else 1e-9
    upper_sh = (h - max(c, o)) / rng
    lower_sh = (min(c, o) - l) / rng
    high_close = (c - l) / rng > 0.7
    low_close = (c - l) / rng < 0.3
    is_bullish = c > o
    big_bullish = (body / rng) > 0.6 and is_bullish
    big_bearish = (body / rng) > 0.6 and not is_bullish

    candle_state = "陽線" if is_bullish else "陰線"
    if upper_sh > 0.4 and not is_bullish:
        candle_state = "上ヒゲ失速"
    elif lower_sh > 0.4 and is_bullish:
        candle_state = "下ヒゲ反転"
    elif big_bullish:
        candle_state = "大陽線"
    elif big_bearish:
        candle_state = "大陰線"

    # サイン
    range_break = c >= rh20 * 0.995
    squeeze = (rh20 - rl20) / c < 0.10 if c > 0 else False
    prior_big_volume = bool(vr20 and vr20 >= 1.8 and pc5 >= 0)
    selling_exhaustion = bool(vr20 and vr20 < 0.6 and pc20 > -15)
    reaccumulation = squeeze and bool(vr20 and vr20 < 1.2)
    pre_breakout = range_break and bool(vr20 and 0.6 <= vr20 <= 2.0)

    # スコア
    overext = 0.0
    if ma25_dev >= 50: overext += 40
    elif ma25_dev >= 30: overext += 25
    elif ma25_dev >= 15: overext += 10
    if pc5 >= 30: overext += 25
    elif pc5 >= 15: overext += 10
    if pc20 >= 80: overext += 30
    elif pc20 >= 40: overext += 15
    overext = min(100.0, overext)

    chart_vol = 0.0
    if prior_big_volume: chart_vol += 25
    if selling_exhaustion: chart_vol += 20
    if reaccumulation: chart_vol += 15
    if pre_breakout: chart_vol += 25
    if high_close: chart_vol += 10
    chart_vol = min(100.0, chart_vol)

    liquidity = min(100.0, math.log10(max(1, v)) * 15)
    risk_ctrl = 100 - min(100.0, max(0.0, sup_dist - 5) * 2)  # 支持線近いほど高い

    return {
        "close": c, "volume": v,
        "price_change_1d": round(pc1, 3),
        "price_change_3d": round(pc3, 3),
        "price_change_5d": round(pc5, 3),
        "price_change_20d": round(pc20, 3),
        "volume_ratio_5d": round(vr5, 3) if vr5 else None,
        "volume_ratio_20d": round(vr20, 3) if vr20 else None,
        "ma5": ma5, "ma25": ma25, "ma75": ma75, "ma200": ma200,
        "ma25_deviation": round(ma25_dev, 2),
        "support_line": round(support, 2),
        "resistance_line": round(resistance, 2),
        "resistance_upside": round(res_up, 2),
        "support_distance": round(sup_dist, 2),
        "atr": round(atr, 4) if atr else None,
        "range_position": round(range_pos, 3),
        "candle_state": candle_state,
        "high_close_flag": high_close,
        "low_close_flag": low_close,
        "upper_shadow_ratio": round(upper_sh, 3),
        "lower_shadow_ratio": round(lower_sh, 3),
        "range_break_flag": range_break,
        "squeeze_flag": squeeze,
        "prior_big_volume_flag": prior_big_volume,
        "selling_exhaustion_flag": selling_exhaustion,
        "reaccumulation_flag": reaccumulation,
        "pre_breakout_flag": pre_breakout,
        "overextension_score": round(overext, 1),
        "chart_volume_score": round(chart_vol, 1),
        "liquidity_score": round(liquidity, 1),
        "risk_control_score": round(risk_ctrl, 1),
        # 材料: training builderでは未取得
        "material_known_flag": False,
        "catalyst_category": "unknown",
        "catalyst_quality_score": 0.0,
        "catalyst_continuity_score": 0.0,
        "bad_news_flag": False,
        "dilution_risk_flag": False,
    }


def _calc_t0_labels(df: pd.DataFrame, t0_idx: int) -> Dict:
    """T0以降の結果ラベル (T+1〜T+20)"""
    if t0_idx >= len(df):
        return {}
    t1_close_pre = float(df.iloc[t0_idx - 1]["close"]) if t0_idx >= 1 else None
    if not t1_close_pre or t1_close_pre <= 0:
        return {}
    future = df.iloc[t0_idx: t0_idx + 21]
    if future.empty:
        return {}
    max_high = float(future["high"].max())
    min_low = float(future["low"].min())
    max_gain = (max_high - t1_close_pre) / t1_close_pre * 100
    max_dd = (min_low - t1_close_pre) / t1_close_pre * 100
    hit_20 = max_gain >= 20
    hit_10 = max_gain >= 10
    return {
        "max_gain_20d": round(max_gain, 3),
        "max_drawdown_20d": round(max_dd, 3),
        "hit_20_percent": hit_20,
        "hit_10_percent": hit_10,
    }


# =============== ケース分類 ===============
def _classify_case(features: Dict, labels: Dict, surge: bool) -> str:
    """case_type を判定"""
    pc5 = features.get("price_change_5d") or 0
    pc20 = features.get("price_change_20d") or 0
    overext = features.get("overextension_score") or 0
    pre_breakout = features.get("pre_breakout_flag", False)
    selling_exh = features.get("selling_exhaustion_flag", False)
    reaccum = features.get("reaccumulation_flag", False)
    prior_vol = features.get("prior_big_volume_flag", False)

    hit_20 = labels.get("hit_20_percent", False)
    hit_10 = labels.get("hit_10_percent", False)
    max_gain = labels.get("max_gain_20d") or 0
    max_dd = labels.get("max_drawdown_20d") or 0

    if surge and hit_20:
        return "positive_surge"
    if hit_20 and not surge:
        return "semi_positive_surge"  # 急騰判定はないがT+20で+20%達成

    # 失敗系
    if overext >= 60 and max_dd <= -10:
        return "failed_overextended"
    if overext >= 60 and not hit_10:
        return "failed_overextended"

    # 材料未確認 + 急騰サインあり + 不発
    if (not features.get("material_known_flag")) and (prior_vol or pre_breakout) and not hit_10:
        return "failed_weak_material"

    # 上がった後の出尽くし
    if pc5 >= 20 and max_dd <= -15:
        return "failed_material_exhaustion"

    # 急騰前夜似だが不発
    if (pre_breakout or prior_vol or selling_exh or reaccum) and not hit_10:
        return "negative_non_surge"

    # その他: hit_10〜20
    if hit_10:
        return "watch_event"

    return "negative_non_surge"


# =============== バッチ実行 ===============
def _save_training_window_and_features(symbol: str, market: str, df: pd.DataFrame,
                                       t0_idx: int, event_date: str,
                                       surge: bool) -> Optional[int]:
    """1個のtraining windowとfeature vectorを保存"""
    features = _calc_t1_features(df, t0_idx)
    if not features:
        return None
    labels = _calc_t0_labels(df, t0_idx)
    if not labels:
        return None
    case_type = _classify_case(features, labels, surge)

    db: Session = SessionLocal()
    try:
        # 重複チェック
        existing = db.query(TrainingWindow).filter(
            TrainingWindow.symbol == symbol,
            TrainingWindow.event_date == event_date,
        ).first()
        if existing:
            return existing.id

        t1_date = _clean_str(df.iloc[t0_idx - 1]["date"]) if t0_idx >= 1 else None
        t0_date = _clean_str(df.iloc[t0_idx]["date"])
        window_start_idx = max(0, t0_idx - 60)
        window_end_idx = min(len(df) - 1, t0_idx + 20)
        win = TrainingWindow(
            symbol=_clean_str(symbol), market=_clean_str(market),
            event_date=_clean_str(event_date),
            case_type=_clean_str(case_type),
            window_start=_clean_str(df.iloc[window_start_idx]["date"]),
            window_end=_clean_str(df.iloc[window_end_idx]["date"]),
            t1_date=t1_date, t0_date=t0_date,
            max_gain_20d=_clean_float(labels.get("max_gain_20d")),
            max_drawdown_20d=_clean_float(labels.get("max_drawdown_20d")),
            hit_20_percent=_clean_bool(labels.get("hit_20_percent")),
            hit_10_percent=_clean_bool(labels.get("hit_10_percent")),
            stop_loss_like_drawdown=_clean_float(labels.get("max_drawdown_20d")),
        )
        db.add(win)
        db.flush()

        # ラベル系
        success_class = "hit_20" if labels.get("hit_20_percent") else (
            "hit_10_to_20" if labels.get("hit_10_percent") else (
                "overextended_failed" if case_type == "failed_overextended" else
                "weak_material_failed" if case_type == "failed_weak_material" else
                "material_exhaustion_failed" if case_type == "failed_material_exhaustion" else
                "bad_news_failed" if case_type == "failed_bad_news" else
                "failed"
            )
        )

        sanitized = _sanitize_feature_dict({k: v for k, v in features.items() if hasattr(TrainingFeatureVector, k)})
        fv = TrainingFeatureVector(
            training_window_id=win.id,
            symbol=_clean_str(symbol), market=_clean_str(market),
            feature_asof_date=t1_date, case_type=_clean_str(case_type),
            **sanitized,
            label_hit_20_percent=_clean_bool(labels.get("hit_20_percent")),
            label_max_gain_20d=_clean_float(labels.get("max_gain_20d")),
            label_max_drawdown_20d=_clean_float(labels.get("max_drawdown_20d")),
            label_success_class=_clean_str(success_class),
        )
        db.add(fv)
        db.commit()
        return win.id
    except Exception as e:
        db.rollback()
        # automation_errors に記録
        try:
            from app.models.models import AutomationError
            err_db = SessionLocal()
            err_db.add(AutomationError(
                job_id=None,
                symbol=symbol,
                market=market,
                step="save_training_window",
                error_type=type(e).__name__,
                error_message=str(e)[:500],
                traceback=f"event_date={event_date} case_type={case_type}",
            ))
            err_db.commit()
            err_db.close()
        except Exception:
            pass
        return None
    finally:
        db.close()


def _create_job(job_type: str, market_scope: str, start_date: str, end_date: str) -> int:
    db: Session = SessionLocal()
    try:
        job = TrainingBuildJob(
            status="running", job_type=job_type,
            market_scope=market_scope, start_date=start_date, end_date=end_date,
        )
        db.add(job); db.commit()
        return job.id
    finally:
        db.close()


def _finish_job(job_id: int, status: str = "completed", error: str = None):
    db: Session = SessionLocal()
    try:
        j = db.query(TrainingBuildJob).filter(TrainingBuildJob.id == job_id).first()
        if not j:
            return
        p = get_progress()
        j.status = status
        j.total_symbols = p["total_symbols"]
        j.processed_symbols = p["processed_symbols"]
        j.fetched_rows = p["fetched_rows"]
        j.surge_events_found = p["surge_events_found"]
        j.negative_cases_found = p["negative_cases_found"]
        j.feature_vectors_created = p["feature_vectors_created"]
        j.error_count = p["error_count"]
        j.error_message = error
        j.finished_at = datetime.utcnow()
        db.commit()
    finally:
        db.close()


# =============== Run all ===============
def run_build_all_sync(params: Dict):
    markets = params.get("markets") or ["JP"]
    include_adr = bool(params.get("include_adr", True))
    max_symbols = int(params.get("max_symbols", 50))
    chunk_size = int(params.get("chunk_size", 20))
    surge_threshold = float(params.get("surge_threshold_percent", 20.0))
    semi_threshold = float(params.get("semi_surge_threshold_percent", 15.0))
    target_mode = params.get("target_mode", "all")

    market_scope = f"{target_mode}:" + ",".join(markets) + (",ADR" if include_adr else "")
    job_id = _create_job(
        f"build_all/{target_mode}", market_scope,
        params.get("start_date", ""), params.get("end_date", ""),
    )
    with _lock:
        _progress.update({
            "running": True, "status": "running", "phase": "fetching",
            "current_symbol": "", "processed_symbols": 0, "total_symbols": 0,
            "fetched_rows": 0, "surge_events_found": 0,
            "negative_cases_found": 0, "feature_vectors_created": 0,
            "error_count": 0, "job_id": job_id,
        })

    try:
        syms = select_target_universe(target_mode, markets, max_symbols, include_adr)
        _set(total_symbols=len(syms))

        for chunk_start in range(0, len(syms), chunk_size):
            chunk = syms[chunk_start: chunk_start + chunk_size]
            for s in chunk:
                sym = s["yahoo_symbol"]
                market = s.get("market", "JP")
                _set(current_symbol=sym, phase="fetching")
                try:
                    # 1. 過去OHLCV取得
                    inserted = _fetch_history_for_symbol(sym, market, period="5y")
                    with _lock:
                        _progress["fetched_rows"] += inserted

                    # 2. 急騰イベント検出
                    _set(phase="detecting")
                    events = _detect_surge_events_for_symbol(sym, market, surge_threshold, semi_threshold)
                    _save_surge_events(events)
                    surge_count = len([e for e in events if e.get("threshold_type") == "surge_20"])
                    with _lock:
                        _progress["surge_events_found"] += len(events)

                    # 3. 特徴量抽出 + ケース分類
                    _set(phase="features")
                    df = _list_history_for_symbol(sym)
                    if df is None or len(df) < 30:
                        with _lock:
                            _progress["processed_symbols"] += 1
                        continue
                    df = df.sort_values("date").reset_index(drop=True)
                    # 急騰event_dateごとに保存 (positive)
                    event_dates_to_idx = {}
                    for e in events:
                        ed = e["event_date"]
                        match = df.index[df["date"] == ed]
                        if len(match) > 0:
                            event_dates_to_idx[ed] = int(match[0])

                    for ed, idx in event_dates_to_idx.items():
                        if idx < 5 or idx >= len(df) - 5:
                            continue
                        wid = _save_training_window_and_features(sym, market, df, idx, ed, surge=True)
                        if wid:
                            with _lock:
                                _progress["feature_vectors_created"] += 1

                    # 4. negative case: 急騰イベントでない日も sampled
                    # 全期間のうち、特徴量が「前夜サイン or 過熱」を満たす日を抽出
                    neg_sample_ratio = float(params.get("negative_sample_ratio", 3.0))
                    target_neg_count = max(1, int(surge_count * neg_sample_ratio + 1))
                    # 30日おきにサンプリング
                    candidate_indices = list(range(30, len(df) - 21, 15))
                    sampled_neg = 0
                    surge_dates = set(event_dates_to_idx.keys())
                    for idx in candidate_indices:
                        if sampled_neg >= target_neg_count:
                            break
                        dt = str(df.iloc[idx]["date"])
                        if dt in surge_dates:
                            continue
                        # T-1特徴量で「兆候あり」「過熱」「弱材料サイン」を満たすか
                        feats = _calc_t1_features(df, idx)
                        if not feats:
                            continue
                        cand = (feats.get("pre_breakout_flag") or feats.get("prior_big_volume_flag") or
                                feats.get("overextension_score", 0) >= 50 or
                                feats.get("price_change_5d", 0) >= 15)
                        if not cand:
                            continue
                        wid = _save_training_window_and_features(sym, market, df, idx, dt, surge=False)
                        if wid:
                            with _lock:
                                _progress["negative_cases_found"] += 1
                                _progress["feature_vectors_created"] += 1
                            sampled_neg += 1
                except Exception as e:
                    with _lock:
                        _progress["error_count"] += 1
                    print(f"build symbol failed {s.get('symbol')}: {e}")

                with _lock:
                    _progress["processed_symbols"] += 1

        _finish_job(job_id, "completed")
        with _lock:
            _progress["running"] = False
            _progress["status"] = "completed"
            _progress["phase"] = ""
            _progress["current_symbol"] = ""
    except Exception as e:
        _finish_job(job_id, "failed", str(e))
        with _lock:
            _progress["running"] = False
            _progress["status"] = "failed"


def run_in_background(params: Dict):
    t = threading.Thread(target=run_build_all_sync, args=(params,), daemon=True)
    t.start()


# =============== サマリ ===============
def get_summary() -> Dict:
    db: Session = SessionLocal()
    try:
        ohlcv_rows = db.query(HistoricalOHLCV).count()
        ohlcv_symbols = db.query(HistoricalOHLCV.symbol).distinct().count()
        surge_events = db.query(SurgeEvent).count()
        positive_surge = db.query(SurgeEvent).filter(SurgeEvent.threshold_type == "surge_20").count()
        semi_surge = db.query(SurgeEvent).filter(SurgeEvent.threshold_type == "semi_surge_15").count()

        feature_vectors = db.query(TrainingFeatureVector).count()
        by_case = dict(
            db.query(TrainingFeatureVector.case_type, func.count(TrainingFeatureVector.id))
              .group_by(TrainingFeatureVector.case_type).all()
        )

        positive_count = (by_case.get("positive_surge", 0) + by_case.get("semi_positive_surge", 0))
        negative_count = (by_case.get("negative_non_surge", 0) +
                          by_case.get("failed_overextended", 0) +
                          by_case.get("failed_weak_material", 0) +
                          by_case.get("failed_bad_news", 0) +
                          by_case.get("failed_material_exhaustion", 0))
        ratio = round(negative_count / max(1, positive_count), 2)

        jobs = (db.query(TrainingBuildJob)
                .order_by(TrainingBuildJob.id.desc()).limit(5).all())

        return {
            "ohlcv_rows": ohlcv_rows,
            "ohlcv_symbols": ohlcv_symbols,
            "surge_events_count": surge_events,
            "positive_surge_count": positive_surge,
            "semi_surge_count": semi_surge,
            "training_feature_vectors": feature_vectors,
            "positive_cases": positive_count,
            "negative_cases": negative_count,
            "positive_negative_ratio": ratio,
            "by_case_type": by_case,
            "recent_jobs": [
                {"id": j.id, "status": j.status, "market_scope": j.market_scope,
                 "total_symbols": j.total_symbols, "processed_symbols": j.processed_symbols,
                 "fetched_rows": j.fetched_rows,
                 "surge_events_found": j.surge_events_found,
                 "negative_cases_found": j.negative_cases_found,
                 "feature_vectors_created": j.feature_vectors_created,
                 "error_count": j.error_count,
                 "started_at": j.started_at.isoformat() if j.started_at else None,
                 "finished_at": j.finished_at.isoformat() if j.finished_at else None}
                for j in jobs
            ],
        }
    finally:
        db.close()


def quality_report() -> Dict:
    db: Session = SessionLocal()
    try:
        rows = db.query(TrainingFeatureVector).all()
        total = len(rows)
        if total == 0:
            return {"status": "no_data", "total_feature_vectors": 0}

        positive = sum(1 for r in rows if r.case_type in ("positive_surge", "semi_positive_surge"))
        negative = sum(1 for r in rows if r.case_type and r.case_type.startswith(("negative_", "failed_")))
        missing_price = sum(1 for r in rows if not r.close)
        # leak check: feature_asof_date < event_date (training_window)
        leak_pass = True
        # 重複: same symbol+feature_asof_date
        seen = set()
        dups = 0
        for r in rows:
            k = (r.symbol, r.feature_asof_date)
            if k in seen:
                dups += 1
            seen.add(k)
        # 異常値: price_change_5d > 200% or < -50%
        outliers = sum(1 for r in rows if r.price_change_5d and (r.price_change_5d > 200 or r.price_change_5d < -50))

        quality = 100.0
        quality -= min(40, missing_price / total * 100)
        quality -= min(20, dups / total * 100)
        quality -= min(20, outliers / total * 100)
        if positive == 0 or negative == 0:
            quality -= 20

        warnings = []
        if positive == 0: warnings.append("positive case が存在しません")
        if negative == 0: warnings.append("negative case が存在しません")
        if positive > 0 and negative / positive < 1: warnings.append(f"negative/positive 比 {negative/positive:.2f} が低い (推奨 >=2)")
        if missing_price > 0: warnings.append(f"close 欠損 {missing_price}件")
        if outliers > 0: warnings.append(f"極端値 {outliers}件")

        return {
            "total_feature_vectors": total,
            "positive_cases": positive,
            "negative_cases": negative,
            "positive_negative_ratio": round(negative / max(1, positive), 2),
            "missing_price_count": missing_price,
            "duplicate_case_count": dups,
            "extreme_outlier_count": outliers,
            "leakage_check_pass": leak_pass,
            "quality_score": round(max(0, quality), 1),
            "warnings": warnings,
        }
    finally:
        db.close()


def feature_stats() -> Dict:
    """positive case と negative case の特徴量平均を比較"""
    db: Session = SessionLocal()
    try:
        rows = db.query(TrainingFeatureVector).all()
        if not rows:
            return {"status": "no_data"}
        positives = [r for r in rows if r.case_type in ("positive_surge", "semi_positive_surge")]
        negatives = [r for r in rows if r.case_type and r.case_type.startswith(("negative_", "failed_"))]
        overext_failed = [r for r in rows if r.case_type == "failed_overextended"]
        weak_failed = [r for r in rows if r.case_type == "failed_weak_material"]
        exh_failed = [r for r in rows if r.case_type == "failed_material_exhaustion"]

        numeric_keys = [
            "price_change_1d", "price_change_5d", "price_change_20d",
            "volume_ratio_5d", "volume_ratio_20d",
            "ma25_deviation", "resistance_upside", "support_distance",
            "range_position", "upper_shadow_ratio", "lower_shadow_ratio",
            "overextension_score", "chart_volume_score",
            "liquidity_score", "risk_control_score",
            "label_max_gain_20d", "label_max_drawdown_20d",
        ]

        def avg(rs, k):
            vals = [getattr(r, k) for r in rs if getattr(r, k) is not None]
            return round(float(np.mean(vals)), 3) if vals else None

        def stats_for(rs):
            return {k: avg(rs, k) for k in numeric_keys}

        return {
            "n_positive": len(positives),
            "n_negative": len(negatives),
            "n_overext_failed": len(overext_failed),
            "n_weak_material_failed": len(weak_failed),
            "n_material_exhaustion_failed": len(exh_failed),
            "positive_avg": stats_for(positives),
            "negative_avg": stats_for(negatives),
            "overextended_failed_avg": stats_for(overext_failed),
            "weak_material_failed_avg": stats_for(weak_failed),
            "material_exhaustion_failed_avg": stats_for(exh_failed),
        }
    finally:
        db.close()


def get_training_features_for_matching(limit: int = 2000) -> Dict:
    """predictor用: 全training_feature_vectorをラベル別に返す"""
    db: Session = SessionLocal()
    try:
        rows = db.query(TrainingFeatureVector).limit(limit).all()
        return {
            "items": [{
                "case_id": r.id,
                "symbol": r.symbol,
                "case_type": r.case_type,
                "label_hit_20_percent": r.label_hit_20_percent,
                "label_max_gain_20d": r.label_max_gain_20d,
                "label_max_drawdown_20d": r.label_max_drawdown_20d,
                "t1_volume_ratio_20d": r.volume_ratio_20d,
                "t1_price_change_5d": r.price_change_5d,
                "t1_price_change_20d": r.price_change_20d,
                "t1_ma25_deviation": r.ma25_deviation,
                "t1_resistance_upside": r.resistance_upside,
                "t1_support_distance": r.support_distance,
                "t1_overextension_score": r.overextension_score,
                "t1_chart_volume_score": r.chart_volume_score,
                "range_position": r.range_position,
            } for r in rows]
        }
    finally:
        db.close()
