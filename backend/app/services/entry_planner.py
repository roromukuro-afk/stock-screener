"""エントリー価格・損切り・利確ゾーン算出エンジン

これは投資助言ではなく、過去の支持線/抵抗線/ATR等から
「もし押し目買いするならこの帯」「もしブレイク追うならここで強気否定」を計算するだけ。
"""
from typing import Dict, Optional


def _safe(v, default=0.0):
    try:
        if v is None: return default
        f = float(v)
        if f != f: return default  # NaN check
        return f
    except (ValueError, TypeError):
        return default


def build_entry_plan(result: Dict) -> Dict:
    """スクリーニング結果から entry_plan を組み立てる。

    入力 result が持つ想定キー:
      price, support_line, resistance_line, recent_high_20,
      recent_low_20, ma25, atr, ma25_deviation, upside_to_resistance,
      support_distance, price_change_5d, price_change_20d, prediction_label,
      overextension_risk_score
    """
    price = _safe(result.get("price"))
    support = _safe(result.get("support_line")) or price * 0.92
    resistance = _safe(result.get("resistance_line")) or price * 1.10
    recent_high_20 = _safe(result.get("recent_high_20")) or resistance
    recent_low_20 = _safe(result.get("recent_low_20")) or support
    ma25 = _safe(result.get("ma25")) or price * 0.98
    atr = _safe(result.get("atr")) or (price * 0.03)
    ma25_dev = _safe(result.get("ma25_deviation"))
    upside = _safe(result.get("upside_to_resistance"))
    overext = _safe(result.get("overextension_risk_score"))
    pc_5 = _safe(result.get("price_change_5d"))
    pc_20 = _safe(result.get("price_change_20d"))
    pred = result.get("prediction_label") or ""

    # 追いかけ禁止判定
    chase_prohibited = (
        overext >= 60 or pc_20 >= 80 or pc_5 >= 30 or
        ma25_dev >= 50 or "上がり切り" in pred or "T0後追い" in pred
    )

    # GU過大警告
    gap_up_warning = pc_5 >= 20

    # エントリーゾーン
    # zone_a: 押し目候補(支持線 〜 支持線+ATR×0.5)
    zone_a_low = round(support, 2)
    zone_a_high = round(support + atr * 0.5, 2)

    # zone_b: 25MA付近の押し目
    zone_b_low = round(ma25 - atr * 0.3, 2)
    zone_b_high = round(ma25 + atr * 0.3, 2)

    # zone_c: 直近高値ブレイク後の Reclaim
    zone_c_low = round(recent_high_20, 2)
    zone_c_high = round(recent_high_20 + atr * 0.5, 2)

    # ブレイクトリガー
    breakout_trigger = round(recent_high_20 * 1.005, 2)  # 直近高値+0.5%
    reclaim_line = round(recent_high_20, 2)

    # 押し目買いゾーン (zone_a + zone_b の合成)
    pullback_low = min(zone_a_low, zone_b_low)
    pullback_high = max(zone_a_high, zone_b_high)

    # 損切り = 支持線割れ
    stop_loss = round(support - atr * 0.5, 2)
    # 無効化 = 直近安値割れ
    invalidation = round(recent_low_20 - atr * 0.3, 2)

    # 利確 = 抵抗線 / +ATR×N / +20% / +30%
    tp1 = round(resistance, 2)
    tp2 = round(price * 1.20, 2)
    tp3 = round(price * 1.30, 2)

    # R/R = (TP - entry) / (entry - SL)
    entry_ref = (zone_a_low + zone_a_high) / 2 if zone_a_low > 0 else price
    rr_denom = entry_ref - stop_loss
    if rr_denom <= 0:
        rr_denom = 0.01
    risk_reward_1 = round((tp1 - entry_ref) / rr_denom, 2)
    risk_reward_2 = round((tp2 - entry_ref) / rr_denom, 2)

    # 追いかけ最大価格 = 25MA + ATR×2 (上がり切る前のライン)
    max_chase = round(ma25 + atr * 2.0, 2) if ma25 > 0 else round(price * 1.05, 2)

    # entry_type
    if chase_prohibited:
        entry_type = "追いかけ禁止 (押し目待ちのみ)"
    elif "急騰前夜" in pred:
        if upside >= 20 and overext < 40:
            entry_type = "押し目待ち + ブレイク確認"
        else:
            entry_type = "ブレイク確認"
    elif "条件付き" in pred:
        entry_type = "小ロット限定 + 押し目待ち"
    elif "イベント監視" in pred:
        entry_type = "イベント確認後"
    elif "二段目" in pred:
        entry_type = "二段目押し目"
    elif "除外" in pred:
        entry_type = "見送り"
    else:
        entry_type = "押し目待ち"

    # ポジションサイズヒント
    if chase_prohibited:
        position_size = "見送り or 極小ロット"
    elif risk_reward_1 < 1.5:
        position_size = "小ロット (R/R不足)"
    elif overext > 40:
        position_size = "通常の半分以下"
    else:
        position_size = "通常ロット"

    # コメント
    comment_bits = []
    if chase_prohibited:
        comment_bits.append("追いかけ禁止: 上がり切り/過熱/T0後追い類似")
    if gap_up_warning:
        comment_bits.append("寄り付きGU過大警告 (寄り買い禁止推奨)")
    if upside < 20:
        comment_bits.append(f"抵抗線まで{upside:.1f}%しか余地なし")
    if risk_reward_1 < 1.5:
        comment_bits.append(f"R/R={risk_reward_1:.2f}と不利")
    if not comment_bits:
        comment_bits.append("過去の支持線/抵抗線/ATRに基づく機械的算出")
    entry_comment = " / ".join(comment_bits)

    return {
        "entry_type": entry_type,
        "entry_zone_a_low": zone_a_low,
        "entry_zone_a_high": zone_a_high,
        "entry_zone_b_low": zone_b_low,
        "entry_zone_b_high": zone_b_high,
        "entry_zone_c_low": zone_c_low,
        "entry_zone_c_high": zone_c_high,
        "breakout_trigger_price": breakout_trigger,
        "reclaim_line": reclaim_line,
        "pullback_buy_zone_low": pullback_low,
        "pullback_buy_zone_high": pullback_high,
        "invalidation_price": invalidation,
        "stop_loss_price": stop_loss,
        "take_profit_1": tp1,
        "take_profit_2": tp2,
        "take_profit_3": tp3,
        "risk_reward_1": risk_reward_1,
        "risk_reward_2": risk_reward_2,
        "max_chase_price": max_chase,
        "chase_prohibited": chase_prohibited,
        "gap_up_warning": gap_up_warning,
        "position_size_hint": position_size,
        "entry_comment": entry_comment,
    }


def build_chart_forecast(result: Dict, entry_plan: Optional[Dict] = None) -> Dict:
    """3シナリオ(強気/基本/弱気)の機械的生成"""
    price = _safe(result.get("price"))
    support = _safe(result.get("support_line")) or price * 0.92
    resistance = _safe(result.get("resistance_line")) or price * 1.10
    atr = _safe(result.get("atr")) or (price * 0.03)
    upside = _safe(result.get("upside_to_resistance"))
    overext = _safe(result.get("overextension_risk_score"))
    pred = result.get("prediction_label") or ""

    ep = entry_plan or build_entry_plan(result)

    # 強気
    bull = {
        "scenario": "強気シナリオ",
        "condition": f"出来高を伴って {ep['breakout_trigger_price']:.2f} 突破→終値で維持",
        "trigger_price": ep["breakout_trigger_price"],
        "support_price": support,
        "resistance_price": resistance,
        "pullback_low": ep["entry_zone_a_low"],
        "pullback_high": ep["entry_zone_a_high"],
        "stop_loss": ep["stop_loss_price"],
        "take_profit_1": ep["take_profit_1"],
        "take_profit_2": ep["take_profit_2"],
        "invalidation": f"出来高急増後の上ヒゲ陰線、または {ep['stop_loss_price']:.2f} 割れ",
        "expected_duration": "数日〜4週間",
        "confidence": "中" if overext < 40 and upside >= 20 else "低",
        "risk_reward": ep["risk_reward_1"],
        "note": "売買指示ではなく分析上の条件です。",
    }
    # 基本
    base = {
        "scenario": "基本シナリオ",
        "condition": f"レンジ ({support:.2f} 〜 {resistance:.2f}) 内で推移",
        "trigger_price": None,
        "support_price": support,
        "resistance_price": resistance,
        "pullback_low": ep["entry_zone_a_low"],
        "pullback_high": ep["entry_zone_a_high"],
        "stop_loss": ep["stop_loss_price"],
        "take_profit_1": (support + resistance) / 2,
        "take_profit_2": resistance,
        "invalidation": f"{ep['stop_loss_price']:.2f} 割れで弱気移行",
        "expected_duration": "2〜4週間",
        "confidence": "中",
        "risk_reward": ep["risk_reward_1"] * 0.6,
        "note": "売買指示ではありません。",
    }
    # 弱気
    bear = {
        "scenario": "弱気シナリオ",
        "condition": f"支持線 {support:.2f} 割れ後の戻り売り、または上値抵抗で失速",
        "trigger_price": support,
        "support_price": round(support * 0.95, 2),
        "resistance_price": resistance,
        "pullback_low": None,
        "pullback_high": None,
        "stop_loss": None,  # 弱気は「買い見送り」
        "take_profit_1": None,
        "take_profit_2": None,
        "invalidation": f"{resistance:.2f} 再ブレイクで弱気否定",
        "expected_duration": "数日",
        "confidence": "中" if overext >= 50 else "低",
        "risk_reward": None,
        "note": "新規買い見送り推奨条件としての分析シナリオです。",
    }
    return {"bull": bull, "base": base, "bear": bear}
