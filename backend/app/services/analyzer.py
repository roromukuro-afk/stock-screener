"""チャート分析・スクリーニング分析サービス"""
import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple


def calc_indicators(df: pd.DataFrame) -> Dict:
    if df is None or len(df) < 5:
        return {}
    close = df["close"].values.astype(float)
    high = df["high"].values.astype(float)
    low = df["low"].values.astype(float)
    volume = df["volume"].values.astype(float)

    def sma(arr, n):
        if len(arr) < n:
            return np.nan
        return float(np.mean(arr[-n:]))

    def safe_last(arr):
        return float(arr[-1]) if len(arr) > 0 else np.nan

    def _clean(v):
        if v is None:
            return None
        try:
            fv = float(v)
            if np.isnan(fv) or np.isinf(fv):
                return None
            return fv
        except (ValueError, TypeError):
            return None

    ma5 = _clean(sma(close, 5))
    ma25 = _clean(sma(close, 25))
    ma75 = _clean(sma(close, 75))
    ma200 = _clean(sma(close, 200))
    vol_avg5 = _clean(sma(volume, 5))
    vol_avg20 = _clean(sma(volume, 20))
    current_close = safe_last(close)
    current_vol = safe_last(volume)

    vol_ratio = current_vol / vol_avg20 if vol_avg20 and vol_avg20 > 0 else 1.0

    price_change_1d = ((close[-1] - close[-2]) / close[-2] * 100) if len(close) >= 2 else 0
    price_change_5d = ((close[-1] - close[-6]) / close[-6] * 100) if len(close) >= 6 else 0
    price_change_20d = ((close[-1] - close[-21]) / close[-21] * 100) if len(close) >= 21 else 0

    ma25_dev = ((current_close - ma25) / ma25 * 100) if ma25 and ma25 > 0 else 0

    recent_high_20 = float(np.max(high[-20:])) if len(high) >= 20 else float(np.max(high))
    recent_low_20 = float(np.min(low[-20:])) if len(low) >= 20 else float(np.min(low))
    recent_high_60 = float(np.max(high[-60:])) if len(high) >= 60 else float(np.max(high))
    recent_low_60 = float(np.min(low[-60:])) if len(low) >= 60 else float(np.min(low))

    support_line = _calc_support(close, low, ma25, recent_low_20, recent_low_60)
    resistance_line = _calc_resistance(close, high, ma25, recent_high_20, recent_high_60)

    upside_to_resistance = ((resistance_line - current_close) / current_close * 100) if resistance_line and current_close > 0 else 0
    support_distance = ((current_close - support_line) / current_close * 100) if support_line and current_close > 0 else 0

    atr = _calc_atr(high, low, close)
    rsi = _calc_rsi(close)

    trend_state = _judge_trend(close, ma5, ma25, ma75)
    range_state = _judge_range(close, high, low, support_line, resistance_line)
    candle_state = _judge_candle(df)
    chart_pattern, chart_pattern2, chart_warning, pattern_conf = _judge_pattern(close, high, low, volume)

    def _r(v, n=2):
        if v is None:
            return None
        try:
            fv = float(v)
            if np.isnan(fv) or np.isinf(fv):
                return None
            return round(fv, n)
        except (ValueError, TypeError):
            return None

    return {
        "ma5": _r(ma5, 4),
        "ma25": _r(ma25, 4),
        "ma75": _r(ma75, 4),
        "ma200": _r(ma200, 4),
        "volume_avg5": _r(vol_avg5, 0),
        "volume_avg20": _r(vol_avg20, 0),
        "volume_ratio": _r(vol_ratio, 2),
        "price_change_1d": round(price_change_1d, 2),
        "price_change_5d": round(price_change_5d, 2),
        "price_change_20d": round(price_change_20d, 2),
        "ma25_deviation": round(ma25_dev, 2),
        "recent_high_20": recent_high_20,
        "recent_low_20": recent_low_20,
        "recent_high_60": recent_high_60,
        "recent_low_60": recent_low_60,
        "support_line": support_line,
        "resistance_line": resistance_line,
        "upside_to_resistance": round(upside_to_resistance, 2),
        "support_distance": round(support_distance, 2),
        "atr": round(atr, 4) if atr else None,
        "rsi": round(rsi, 1) if rsi else None,
        "trend_state": trend_state,
        "range_state": range_state,
        "candle_state": candle_state,
        "chart_pattern_primary": chart_pattern,
        "chart_pattern_secondary": chart_pattern2,
        "chart_pattern_warning": chart_warning,
        "pattern_confidence": pattern_conf,
    }


def _calc_support(close, low, ma25, recent_low_20, recent_low_60) -> float:
    candidates = [v for v in [recent_low_20, recent_low_60, ma25] if v and not np.isnan(v)]
    if not candidates:
        return float(np.min(low[-20:])) if len(low) >= 20 else float(np.min(low))
    return float(max(v for v in candidates if v < close[-1]) if any(v < close[-1] for v in candidates) else min(candidates))


def _calc_resistance(close, high, ma25, recent_high_20, recent_high_60) -> float:
    """抵抗線: 直近20日高値が近すぎる場合は60日高値も考慮し、ブレイク後の値幅余地を返す"""
    curr = close[-1]
    candidates = [v for v in [recent_high_20, recent_high_60] if v and not np.isnan(v) and v > curr]
    if not candidates:
        return float(np.max(high[-60:]) * 1.10) if len(high) >= 60 else float(np.max(high) * 1.10)
    # 20日高値が現在価格の +10% 未満なら、60日高値を採用 (ブレイク後の本格的な値幅)
    near = min(candidates)
    far = max(candidates)
    if (near - curr) / curr < 0.10 and (far - curr) / curr >= 0.10:
        return float(far)
    return float(near)


def _calc_atr(high, low, close, period=14) -> Optional[float]:
    if len(high) < period + 1:
        return None
    trs = []
    for i in range(1, len(high)):
        tr = max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1]))
        trs.append(tr)
    return float(np.mean(trs[-period:]))


def _calc_rsi(close, period=14) -> Optional[float]:
    if len(close) < period + 1:
        return None
    deltas = np.diff(close)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100 - (100 / (1 + rs)))


def _judge_trend(close, ma5, ma25, ma75) -> str:
    if len(close) < 5:
        return "判定不能"
    curr = close[-1]
    if not ma25 or np.isnan(ma25):
        return "判定不能"

    above_ma25 = curr > ma25
    above_ma75 = curr > ma75 if (ma75 and not np.isnan(ma75)) else None
    ma5_above_ma25 = (ma5 > ma25) if (ma5 and not np.isnan(ma5)) else None

    if len(close) >= 5:
        recent_highs = [close[i] > close[i-1] for i in range(-4, 0)]
        uptrend_signals = sum(recent_highs)
    else:
        uptrend_signals = 0

    price_change_20 = ((curr - close[-21]) / close[-21] * 100) if len(close) >= 21 else 0

    if above_ma25 and ma5_above_ma25 and above_ma75 and uptrend_signals >= 3:
        return "上昇トレンド"
    elif not above_ma25 and price_change_20 < -10:
        return "下降トレンド"
    elif abs(price_change_20) < 5 and not (ma5_above_ma25 is True):
        return "横ばいレンジ"
    elif above_ma25 and uptrend_signals >= 2:
        return "上昇トレンド継続"
    elif not above_ma25 and uptrend_signals <= 1:
        return "下降トレンド継続"
    else:
        return "トレンド転換初動"


def _judge_range(close, high, low, support_line, resistance_line) -> str:
    if not support_line or not resistance_line or len(close) < 5:
        return "判定不能"
    curr = close[-1]
    range_size = resistance_line - support_line
    if range_size <= 0:
        return "判定不能"

    pos_in_range = (curr - support_line) / range_size

    if pos_in_range >= 0.85:
        return "レンジ上限接近"
    elif pos_in_range <= 0.15:
        return "レンジ下限反発"
    elif pos_in_range >= 0.5:
        return "レンジ中〜上位"
    else:
        return "レンジ中〜下位"


def _judge_candle(df: pd.DataFrame) -> str:
    if df is None or len(df) < 1:
        return "判定不能"
    row = df.iloc[-1]
    o, h, l, c = float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"])
    body = abs(c - o)
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - l
    range_ = h - l
    if range_ == 0:
        return "判定不能"

    body_ratio = body / range_
    upper_ratio = upper_wick / range_
    lower_ratio = lower_wick / range_

    vol = float(row["volume"]) if "volume" in row else 0
    vol_avg = df["volume"].mean() if "volume" in df.columns else 0
    is_big_vol = vol > vol_avg * 2 if vol_avg > 0 else False

    is_bullish = c > o
    is_big_body = body_ratio > 0.6

    if is_big_vol and upper_ratio > 0.4 and is_bullish:
        return "大商い上ヒゲ"
    if is_big_vol and not is_bullish and is_big_body:
        return "大商い大陰線"
    if is_big_body and is_bullish:
        return "大陽線"
    if is_big_body and not is_bullish:
        return "大陰線"
    if upper_ratio > 0.5 and body_ratio < 0.2:
        return "トンカチ"
    if lower_ratio > 0.5 and body_ratio < 0.2:
        return "逆トンカチ"
    if body_ratio < 0.15:
        return "十字線"
    if lower_ratio > 0.4 and is_bullish:
        return "下ヒゲ反転"
    if upper_ratio > 0.4 and not is_bullish:
        return "上ヒゲ失速"
    return "陽線" if is_bullish else "陰線"


def _judge_pattern(close, high, low, volume) -> Tuple[str, str, str, float]:
    if len(close) < 20:
        return "判定不能", "", "", 0.0

    primary = "判定不能"
    secondary = ""
    warning = ""
    confidence = 0.5

    n = len(close)
    recent = close[-20:]
    recent_high = high[-20:]
    recent_low = low[-20:]

    # ダブルボトム検出
    lows = recent_low
    if len(lows) >= 15:
        min_idx1 = int(np.argmin(lows[:10]))
        min_idx2 = int(np.argmin(lows[10:]) + 10)
        if abs(lows[min_idx1] - lows[min_idx2]) / lows[min_idx1] < 0.03:
            if close[-1] > close[min(min_idx1, min_idx2)]:
                primary = "ダブルボトム"
                confidence = 0.7

    # 逆三尊
    if len(lows) >= 20 and primary == "判定不能":
        thirds = [lows[3], lows[10], lows[17]]
        if thirds[1] < thirds[0] and thirds[1] < thirds[2]:
            if abs(thirds[0] - thirds[2]) / thirds[0] < 0.05:
                primary = "逆三尊"
                confidence = 0.75

    # ボックス
    price_range = (np.max(recent) - np.min(recent)) / np.mean(recent)
    if price_range < 0.1 and primary == "判定不能":
        primary = "ボックス"
        confidence = 0.65

    # ダブルトップ警戒
    highs = recent_high
    if len(highs) >= 15:
        max_idx1 = int(np.argmax(highs[:10]))
        max_idx2 = int(np.argmax(highs[10:]) + 10)
        if abs(highs[max_idx1] - highs[max_idx2]) / highs[max_idx1] < 0.03:
            if close[-1] < highs[max(max_idx1, max_idx2)]:
                warning = "ダブルトップ警戒"

    # 三角保ち合い
    if primary == "判定不能":
        high_trend = np.polyfit(range(len(recent_high[-10:])), recent_high[-10:], 1)[0]
        low_trend = np.polyfit(range(len(recent_low[-10:])), recent_low[-10:], 1)[0]
        if high_trend < 0 and low_trend > 0:
            primary = "三角保ち合い"
            confidence = 0.6

    # フラッグ
    if primary == "判定不能" and len(close) >= 30:
        trend_before = (close[-20] - close[-30]) / close[-30] * 100 if len(close) >= 30 else 0
        consolidation = price_range < 0.08
        if trend_before > 10 and consolidation:
            primary = "フラッグ"
            confidence = 0.65
            secondary = "初動後押し目"

    if primary == "判定不能":
        primary = "特定パターンなし"

    return primary, secondary, warning, confidence


def judge_volume_cycle(df: pd.DataFrame, indicators: Dict) -> str:
    if df is None or len(df) < 5 or not indicators:
        return "判定不能"

    vol_ratio = indicators.get("volume_ratio", 1.0)
    candle = indicators.get("candle_state", "")
    price_change_20d = indicators.get("price_change_20d", 0)
    ma25_dev = indicators.get("ma25_deviation", 0)
    trend = indicators.get("trend_state", "")
    upside = indicators.get("upside_to_resistance", 0)

    if vol_ratio >= 2.5:
        if "上ヒゲ" in candle or "大陰線" in candle:
            return "天井大商い警戒"
        if ma25_dev > 30:
            return "天井大商い警戒"
        return "先行大商い"

    if vol_ratio <= 0.5:
        if price_change_20d > -10:
            return "売り枯れ"
        return "人気離散"

    if vol_ratio > 0.5 and vol_ratio <= 0.8:
        if "下降" not in trend and price_change_20d > -15:
            return "価格維持"

    if vol_ratio > 0.8 and vol_ratio < 1.5:
        if upside >= 20:
            return "再点火待ち"
        return "再点火開始"

    if vol_ratio < 0.3:
        return "出来高不足"

    return "判定不能"


def judge_chart_cycle(indicators: Dict) -> str:
    if not indicators:
        return "判定不能"

    ma25_dev = indicators.get("ma25_deviation", 0)
    upside = indicators.get("upside_to_resistance", 0)
    support_dist = indicators.get("support_distance", 999)
    trend = indicators.get("trend_state", "")
    range_state = indicators.get("range_state", "")
    candle = indicators.get("candle_state", "")
    pattern = indicators.get("chart_pattern_primary", "")
    vol_ratio = indicators.get("volume_ratio", 1.0)
    price_change_20d = indicators.get("price_change_20d", 0)

    if ma25_dev > 50 and price_change_20d > 40:
        return "上がり切り"
    if "支持線割れ" in candle or (support_dist < 0 and trend == "下降トレンド"):
        return "支持線割れ"
    if "三角保ち合い" in pattern or "ボックス" in pattern:
        if upside >= 15:
            return "値幅収縮"
        return "底固め"
    if "ダブルボトム" in pattern or "逆三尊" in pattern:
        return "安値切り上げ"
    if "フラッグ" in pattern or "初動後押し目" in pattern:
        return "初動後押し目"
    if upside >= 20 and vol_ratio < 0.8 and support_dist < 15:
        return "ブレイク直前"
    if upside >= 20 and vol_ratio >= 1.5:
        return "再点火待ち"
    if "レンジ下限" in range_state:
        return "支持線維持"
    if trend == "上昇トレンド" and ma25_dev < 20:
        return "ブレイク済み"
    if support_dist < 10 and upside >= 20:
        return "支持線維持"

    return "判定不能"


def classify_archetype(indicators: Dict, vol_cycle: str, chart_cycle: str, material_status: str) -> Dict:
    main = "判定不能"
    sub = []
    chart_types_list = []
    warning_types_list = []

    ma25_dev = indicators.get("ma25_deviation", 0)
    upside = indicators.get("upside_to_resistance", 0)
    vol_ratio = indicators.get("volume_ratio", 1.0)
    pattern = indicators.get("chart_pattern_primary", "")
    pattern_warning = indicators.get("chart_pattern_warning", "")
    price_change_20d = indicators.get("price_change_20d", 0)
    support_dist = indicators.get("support_distance", 999)
    candle = indicators.get("candle_state", "")

    if vol_cycle == "売り枯れ" or vol_cycle == "価格維持":
        main = "売り枯れ / Selling Exhaustion型"
    elif vol_cycle == "先行大商い":
        main = "先行資金流入 / Pre-Night型"
    elif "ダブルボトム" in pattern or "逆三尊" in pattern:
        main = "悪材料出尽くし / Vacuum Effect型"
    elif material_status == "材料あり":
        main = "受注・大型契約・採用進展型"
    else:
        main = "売り枯れ / Selling Exhaustion型"

    if "ダブルボトム" in pattern:
        chart_types_list.append("ダブルボトム型")
    if "逆三尊" in pattern:
        chart_types_list.append("逆三尊型")
    if "ボックス" in pattern:
        chart_types_list.append("ボックス上放れ型")
    if "三角保ち合い" in pattern:
        chart_types_list.append("三角保ち合い収束型")
    if "フラッグ" in pattern:
        chart_types_list.append("フラッグ型")
    if "初動後押し目" in pattern:
        chart_types_list.append("初動後押し目型")
    if chart_cycle == "支持線維持":
        chart_types_list.append("支持線反発型")
    if upside >= 20 and vol_ratio < 1.5:
        chart_types_list.append("抵抗線突破前型")
    if vol_cycle in ["再点火待ち", "再点火開始"]:
        chart_types_list.append("再点火待ち型")

    if ma25_dev > 50:
        warning_types_list.append("上がり切り警戒")
    if vol_cycle == "天井大商い警戒":
        warning_types_list.append("天井大商い警戒")
    if price_change_20d > 50:
        warning_types_list.append("高値掴み警戒")
    if support_dist < 0:
        warning_types_list.append("支持線割れ警戒")
    if material_status == "材料不明":
        warning_types_list.append("材料不明警戒")
    if "ダブルトップ" in pattern_warning:
        warning_types_list.append("天井大商い警戒")

    return {
        "main_archetype": main,
        "sub_archetypes": sub[:2],
        "chart_types": chart_types_list[:2],
        "warning_types": warning_types_list[:2],
    }


def calc_score(indicators: Dict, vol_cycle: str, chart_cycle: str,
               material_status: str, jpy_price: float, price_limit: float = 3000) -> Dict:
    scores = {
        "upside_score": 0,
        "future_catalyst_score": 0,
        "chart_score": 0,
        "volume_cycle_score": 0,
        "material_theme_score": 0,
        "supply_score": 0,
        "archetype_score": 0,
        "risk_management_score": 0,
    }

    upside = indicators.get("upside_to_resistance", 0)
    support_dist = indicators.get("support_distance", 999)
    ma25_dev = indicators.get("ma25_deviation", 0)
    vol_ratio = indicators.get("volume_ratio", 1.0)
    candle = indicators.get("candle_state", "")
    pattern = indicators.get("chart_pattern_primary", "")
    rsi = indicators.get("rsi", 50)
    price_change_20d = indicators.get("price_change_20d", 0)
    trend = indicators.get("trend_state", "")

    # 上値余地スコア (15点満点)
    if upside >= 30:
        scores["upside_score"] = 15
    elif upside >= 25:
        scores["upside_score"] = 12
    elif upside >= 20:
        scores["upside_score"] = 8
    elif upside >= 15:
        scores["upside_score"] = 4
    else:
        scores["upside_score"] = 0

    # 未来急騰予兆スコア (15点満点)
    catalyst = 0
    if vol_cycle in ["再点火開始", "再点火待ち"]:
        catalyst += 8
    if chart_cycle in ["値幅収縮", "ブレイク直前", "安値切り上げ"]:
        catalyst += 7
    elif chart_cycle in ["初動後押し目", "支持線維持"]:
        catalyst += 4
    scores["future_catalyst_score"] = min(15, catalyst)

    # チャート構造スコア (15点満点)
    chart = 0
    if "ダブルボトム" in pattern or "逆三尊" in pattern:
        chart += 12
    elif "三角保ち合い" in pattern or "ボックス" in pattern:
        chart += 9
    elif "フラッグ" in pattern:
        chart += 8
    elif pattern not in ["判定不能", "特定パターンなし"]:
        chart += 5
    if ma25_dev < 20:
        chart += 3
    elif ma25_dev < 35:
        chart += 1
    scores["chart_score"] = min(15, chart)

    # 出来高サイクルスコア (15点満点)
    vc_map = {
        "再点火開始": 15,
        "再点火待ち": 12,
        "価格維持": 10,
        "売り枯れ": 8,
        "先行大商い": 6,
        "出来高不足": 2,
        "天井大商い警戒": 0,
        "人気離散": 1,
        "判定不能": 3,
    }
    scores["volume_cycle_score"] = vc_map.get(vol_cycle, 3)

    # 材料・テーマスコア (10点満点)
    mat_map = {
        "材料あり": 10,
        "続報期待": 8,
        "テーマのみ": 6,
        "材料不明": 3,
        "材料なし": 1,
        "決算接近": 4,
    }
    scores["material_theme_score"] = mat_map.get(material_status, 3)

    # 需給の軽さスコア (10点満点)
    supply = 5
    if jpy_price < 500:
        supply += 4
    elif jpy_price < 1000:
        supply += 3
    elif jpy_price < 2000:
        supply += 2
    elif jpy_price < 3000:
        supply += 1
    if vol_ratio < 0.5:
        supply += 1
    scores["supply_score"] = min(10, supply)

    # アーキタイプスコア (10点満点)
    arch = 5
    if vol_cycle in ["売り枯れ", "価格維持", "再点火待ち"]:
        arch += 3
    if chart_cycle in ["値幅収縮", "底固め", "初動後押し目"]:
        arch += 2
    scores["archetype_score"] = min(10, arch)

    # リスク管理スコア (10点満点)
    risk = 5
    if support_dist < 10 and support_dist > 0:
        risk += 3
    elif support_dist < 15:
        risk += 1
    if ma25_dev < 25:
        risk += 2
    elif ma25_dev > 50:
        risk -= 3
    scores["risk_management_score"] = max(0, min(10, risk))

    total = sum(scores.values())
    scores["total_score"] = round(total, 1)

    if total >= 85:
        classification = "採用候補"
    elif total >= 75:
        classification = "条件付き候補"
    elif total >= 65:
        classification = "監視候補"
    else:
        classification = "低スコア"

    scores["classification"] = classification
    return scores


def build_warning_flags(indicators: Dict, vol_cycle: str, chart_cycle: str, jpy_price: float) -> List[str]:
    flags = []
    ma25_dev = indicators.get("ma25_deviation", 0)
    price_change_20d = indicators.get("price_change_20d", 0)
    candle = indicators.get("candle_state", "")
    support_dist = indicators.get("support_distance", 999)
    upside = indicators.get("upside_to_resistance", 0)
    vol_ratio = indicators.get("volume_ratio", 1.0)

    if ma25_dev >= 50:
        flags.append("25MA乖離+50%以上")
    if price_change_20d >= 50:
        flags.append("短期+50%上昇済み")
    if "大商い上ヒゲ" in candle:
        flags.append("大商い上ヒゲ")
    if "大商い大陰線" in candle:
        flags.append("大商い大陰線")
    if vol_cycle == "天井大商い警戒":
        flags.append("天井大商い警戒")
    if chart_cycle == "上がり切り":
        flags.append("上がり切り警戒")
    if support_dist < 0:
        flags.append("支持線割れ")
    if upside < 15 and upside >= 0:
        flags.append("上値余地不足")

    return flags


def generate_ai_comment(symbol: str, indicators: Dict, vol_cycle: str, chart_cycle: str,
                        material_status: str, score: float, classification: str,
                        archetype: Dict, warning_flags: List[str]) -> str:
    name = symbol
    upside = indicators.get("upside_to_resistance", 0)
    ma25_dev = indicators.get("ma25_deviation", 0)
    support_dist = indicators.get("support_distance", 999)
    pattern = indicators.get("chart_pattern_primary", "")
    trend = indicators.get("trend_state", "")
    candle = indicators.get("candle_state", "")

    lines = [f"【{name}】 分類:{classification} スコア:{score}/100"]
    lines.append(f"トレンド:{trend} / 出来高サイクル:{vol_cycle} / チャートサイクル:{chart_cycle}")
    lines.append(f"チャートパターン:{pattern} / 最新ローソク足:{candle}")
    lines.append(f"25MA乖離:{ma25_dev:.1f}% / 上値余地:{upside:.1f}% / 支持線距離:{support_dist:.1f}%")

    if warning_flags:
        lines.append(f"⚠️ 警告: {', '.join(warning_flags)}")

    lines.append(f"材料状況: {material_status}")
    lines.append("※これは投資助言ではなく分析・学習目的の自動分析結果です。最終判断はユーザー自身が行ってください。")

    return "\n".join(lines)
