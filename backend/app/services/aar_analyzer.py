"""急騰銘柄AAR自動分析サービス

ユーザーが (symbol, market, move_date, move_percent) を与えると、
T-80〜T+20 のOHLCVを取得してT-3〜T-1の特徴量を抽出し、
T-1時点で観測可能だった情報だけでセットアップ・分類・判定を行う。

T0以降のデータは結果ラベル(t0_result_move_percent, hit_20_percent等)としてのみ保存し、
予測特徴量には混ぜない。
"""
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
import math
import numpy as np
import pandas as pd

from app.services.price_fetcher import get_stock_data


# ===== ユーティリティ =====
def _safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _yahoo_symbol(symbol: str, market: str) -> str:
    if market == "JP" and not symbol.endswith(".T"):
        # 4桁数字なら .T 追加
        if symbol.isdigit() and len(symbol) >= 4:
            return f"{symbol}.T"
    return symbol


def _fetch_ohlcv(yahoo_sym: str, market: str, move_date: str) -> Optional[pd.DataFrame]:
    """T-80〜T+20 を含むに足る OHLCV を取得"""
    # period="1y" で十分(過去1年のデータ)。本実装はサンプル/yfinance 両対応
    df = get_stock_data(yahoo_sym, period="1y", market=market)
    if df is None or len(df) < 20:
        return None
    df = df.sort_values("date").reset_index(drop=True)
    return df


def _find_t0_index(df: pd.DataFrame, move_date: str) -> Optional[int]:
    """move_date またはそれ以前の最も近い取引日のインデックス"""
    # 完全一致を優先
    matches = df.index[df["date"].astype(str) == move_date]
    if len(matches) > 0:
        return int(matches[0])
    # 完全一致なし → move_date 以下の最大日付
    df_filtered = df[df["date"].astype(str) <= move_date]
    if len(df_filtered) > 0:
        return int(df_filtered.index[-1])
    return None


# ===== T-1時点特徴量抽出 =====
def extract_t1_features(df: pd.DataFrame, t0_idx: int) -> Dict:
    """T-1 (t0_idx - 1) 時点で観測可能だった情報のみを使って特徴量を計算"""
    if t0_idx < 5:
        return {"error": "insufficient data before T0"}

    t1_idx = t0_idx - 1
    # T-1 までのデータだけを slice (T0以降は使わない)
    pre = df.iloc[: t1_idx + 1].copy()

    closes = pre["close"].astype(float).values
    highs = pre["high"].astype(float).values
    lows = pre["low"].astype(float).values
    volumes = pre["volume"].astype(float).values
    opens = pre["open"].astype(float).values

    def sma(arr, n):
        if len(arr) < n:
            return None
        return float(np.mean(arr[-n:]))

    t1_close = float(closes[-1])
    t1_open = float(opens[-1])
    t1_high = float(highs[-1])
    t1_low = float(lows[-1])
    t1_volume = float(volumes[-1])

    ma5 = sma(closes, 5)
    ma25 = sma(closes, 25)
    ma75 = sma(closes, 75)
    ma200 = sma(closes, 200)
    vol_avg20 = sma(volumes, 20)
    vol_avg5 = sma(volumes, 5)

    vol_ratio_t1 = (t1_volume / vol_avg20) if vol_avg20 and vol_avg20 > 0 else None
    vol_ratio_t2 = (float(volumes[-2]) / vol_avg20) if vol_avg20 and vol_avg20 > 0 and len(volumes) >= 2 else None
    vol_ratio_t3 = (float(volumes[-3]) / vol_avg20) if vol_avg20 and vol_avg20 > 0 and len(volumes) >= 3 else None

    pc_1d = ((closes[-1] - closes[-2]) / closes[-2] * 100) if len(closes) >= 2 else 0.0
    pc_3d = ((closes[-1] - closes[-4]) / closes[-4] * 100) if len(closes) >= 4 else 0.0
    pc_5d = ((closes[-1] - closes[-6]) / closes[-6] * 100) if len(closes) >= 6 else 0.0
    pc_20d = ((closes[-1] - closes[-21]) / closes[-21] * 100) if len(closes) >= 21 else 0.0

    ma5_dev = ((t1_close - ma5) / ma5 * 100) if ma5 else None
    ma25_dev = ((t1_close - ma25) / ma25 * 100) if ma25 else None

    recent_high_20 = float(np.max(highs[-20:])) if len(highs) >= 20 else float(np.max(highs))
    recent_low_20 = float(np.min(lows[-20:])) if len(lows) >= 20 else float(np.min(lows))
    recent_high_60 = float(np.max(highs[-60:])) if len(highs) >= 60 else float(np.max(highs))
    recent_low_60 = float(np.min(lows[-60:])) if len(lows) >= 60 else float(np.min(lows))

    # 抵抗線・支持線
    resistance = recent_high_20 if recent_high_20 > t1_close else recent_high_60
    if resistance <= t1_close:
        resistance = t1_close * 1.20
    resistance_upside = (resistance - t1_close) / t1_close * 100

    support_candidates = [v for v in [recent_low_20, ma25, ma75] if v and v < t1_close]
    support = max(support_candidates) if support_candidates else recent_low_20
    support_distance = (t1_close - support) / t1_close * 100 if support else None

    # T-1のローソク足判定
    body = abs(t1_close - t1_open)
    range_ = t1_high - t1_low if t1_high > t1_low else 1e-9
    upper_shadow = t1_high - max(t1_close, t1_open)
    lower_shadow = min(t1_close, t1_open) - t1_low
    is_high_close = (t1_close - t1_low) / range_ > 0.7
    is_lower_shadow = (lower_shadow / range_ > 0.3) and (t1_close >= t1_open)
    is_upper_shadow = (upper_shadow / range_ > 0.3) and (t1_close < t1_open)
    is_range_break = t1_close > recent_high_20 * 0.99

    # 上がり切りスコア (0-100)
    overext = 0.0
    if ma25_dev is not None:
        if ma25_dev >= 50:
            overext += 40
        elif ma25_dev >= 30:
            overext += 25
        elif ma25_dev >= 15:
            overext += 10
    if pc_5d >= 30:
        overext += 25
    elif pc_5d >= 15:
        overext += 10
    if pc_20d >= 80:
        overext += 30
    elif pc_20d >= 40:
        overext += 15
    overext = min(100.0, overext)

    return {
        "t1_close": _safe_float(t1_close),
        "t1_volume": _safe_float(t1_volume),
        "t1_volume_ratio_20d": _safe_float(vol_ratio_t1),
        "t2_volume_ratio_20d": _safe_float(vol_ratio_t2),
        "t3_volume_ratio_20d": _safe_float(vol_ratio_t3),
        "t1_price_change_1d": _safe_float(pc_1d),
        "t1_price_change_3d": _safe_float(pc_3d),
        "t1_price_change_5d": _safe_float(pc_5d),
        "t1_price_change_20d": _safe_float(pc_20d),
        "t1_ma5_deviation": _safe_float(ma5_dev),
        "t1_ma25_deviation": _safe_float(ma25_dev),
        "t1_support_distance": _safe_float(support_distance),
        "t1_resistance_upside": _safe_float(resistance_upside),
        "t1_range_break_flag": bool(is_range_break),
        "t1_high_close_flag": bool(is_high_close),
        "t1_lower_shadow_flag": bool(is_lower_shadow),
        "t1_upper_shadow_flag": bool(is_upper_shadow),
        "t1_overextension_score": _safe_float(overext),
        # 追加: 内部利用
        "_ma5": ma5,
        "_ma25": ma25,
        "_ma75": ma75,
        "_support": support,
        "_resistance": resistance,
        "_recent_high_20": recent_high_20,
        "_recent_low_20": recent_low_20,
        "_t1_open": t1_open,
        "_t1_high": t1_high,
        "_t1_low": t1_low,
    }


def extract_t0_to_future_labels(df: pd.DataFrame, t0_idx: int) -> Dict:
    """T0以降の結果ラベル(教師ラベル用、予測特徴量には混ぜないこと)"""
    if t0_idx >= len(df):
        return {}
    t0_close = float(df.iloc[t0_idx]["close"])
    t1_close_prev = float(df.iloc[t0_idx - 1]["close"]) if t0_idx >= 1 else t0_close
    t0_open = float(df.iloc[t0_idx]["open"])
    t0_high = float(df.iloc[t0_idx]["high"])
    t0_volume = float(df.iloc[t0_idx]["volume"])

    t0_move_pct = (t0_close - t1_close_prev) / t1_close_prev * 100 if t1_close_prev > 0 else None
    t0_gap_up = (t0_open - t1_close_prev) / t1_close_prev * 100 if t1_close_prev > 0 else None
    t0_high_close = (t0_close - df.iloc[t0_idx]["low"]) / (t0_high - df.iloc[t0_idx]["low"] + 1e-9) > 0.7

    # 5日後・20日後の最大上昇率
    def max_gain_to(n):
        end_idx = min(t0_idx + n, len(df) - 1)
        if end_idx <= t0_idx:
            return None
        future = df.iloc[t0_idx + 1: end_idx + 1]
        if future.empty:
            return None
        max_high = float(future["high"].max())
        return (max_high - t1_close_prev) / t1_close_prev * 100 if t1_close_prev > 0 else None

    def max_drawdown_to(n):
        end_idx = min(t0_idx + n, len(df) - 1)
        if end_idx <= t0_idx:
            return None
        future = df.iloc[t0_idx + 1: end_idx + 1]
        if future.empty:
            return None
        min_low = float(future["low"].min())
        return (min_low - t1_close_prev) / t1_close_prev * 100 if t1_close_prev > 0 else None

    max_5d = max_gain_to(5)
    max_20d = max_gain_to(20)
    dd_20d = max_drawdown_to(20)

    return {
        "t0_result_move_percent": _safe_float(t0_move_pct),
        "t0_gap_up_percent": _safe_float(t0_gap_up),
        "t0_high_close_flag": bool(t0_high_close),
        "t0_volume": _safe_float(t0_volume),
        "t1_to_t5_max_gain": _safe_float(max_5d),
        "t1_to_t20_max_gain": _safe_float(max_20d),
        "t1_to_t20_max_drawdown": _safe_float(dd_20d),
        "hit_20_percent": (max_20d is not None and max_20d >= 20),
    }


# ===== セットアップ分類 =====
def classify_setup(features: Dict, t0_move: Optional[float]) -> Dict:
    """T-1特徴量からセットアップ型・出来高型・チャート型を分類"""
    vol_r_t1 = features.get("t1_volume_ratio_20d") or 0
    vol_r_t2 = features.get("t2_volume_ratio_20d") or 0
    vol_r_t3 = features.get("t3_volume_ratio_20d") or 0
    pc_5 = features.get("t1_price_change_5d") or 0
    pc_20 = features.get("t1_price_change_20d") or 0
    ma25_dev = features.get("t1_ma25_deviation") or 0
    overext = features.get("t1_overextension_score") or 0
    is_break = features.get("t1_range_break_flag", False)
    is_high_close = features.get("t1_high_close_flag", False)
    is_lower = features.get("t1_lower_shadow_flag", False)
    is_upper = features.get("t1_upper_shadow_flag", False)
    res_up = features.get("t1_resistance_upside") or 0
    sup_dist = features.get("t1_support_distance") or 0

    # 出来高型
    if vol_r_t1 >= 2.5 or vol_r_t2 >= 2.5 or vol_r_t3 >= 2.5:
        if pc_5 >= 15:
            volume_type = "先行大商い"
        else:
            volume_type = "出来高先行"
    elif vol_r_t1 < 0.6 and pc_5 > -10:
        volume_type = "売り枯れ"
    elif 0.6 <= vol_r_t1 < 1.2 and pc_20 > -10:
        volume_type = "価格維持"
    elif vol_r_t1 >= 1.2 and not (overext > 50):
        volume_type = "再点火開始"
    elif overext > 60 and vol_r_t1 >= 2:
        volume_type = "天井大商い警戒"
    else:
        volume_type = "通常"

    # チャート型
    if is_break and is_high_close and overext < 40:
        chart_type = "ブレイク前"
    elif is_lower:
        chart_type = "下ヒゲ反転"
    elif is_upper:
        chart_type = "上ヒゲ失速"
    elif res_up >= 20 and overext < 40 and sup_dist < 15:
        chart_type = "初動後押し目"
    elif res_up >= 25 and vol_r_t1 < 1.2:
        chart_type = "値幅収縮"
    elif overext > 60:
        chart_type = "上がり切り"
    else:
        chart_type = "横ばい"

    # セットアップ型
    if volume_type == "先行大商い" and is_break:
        setup_type = "先行大商い+ブレイク"
    elif volume_type == "売り枯れ" and chart_type in ("初動後押し目", "下ヒゲ反転"):
        setup_type = "売り枯れ底値型"
    elif volume_type == "価格維持" and chart_type == "値幅収縮":
        setup_type = "値幅収縮型"
    elif is_break and is_high_close:
        setup_type = "ブレイクアウト型"
    elif overext > 60:
        setup_type = "上がり切り型"
    elif t0_move is not None and t0_move >= 30 and vol_r_t1 < 1.2:
        setup_type = "T0初動のみ型"
    else:
        setup_type = "一般急騰型"

    return {
        "volume_type": volume_type,
        "chart_type": chart_type,
        "setup_type": setup_type,
    }


# ===== 材料分析 (CSVの 急騰理由 と ニュース出典を活用) =====
def analyze_catalyst(catalyst_text: Optional[str], news_source: Optional[str]) -> Dict:
    """CSVの材料テキストから推定。空欄 → 材料不明"""
    text = (catalyst_text or "").strip()
    src = (news_source or "").strip()

    if not text and not src:
        return {
            "catalyst_category": "公式材料なし",
            "catalyst_timing": "不明",
            "catalyst_strength_score": 10.0,
            "catalyst_continuity_score": 10.0,
            "material_confirmed": False,
            "material_source_rank": "なし",
            "weak_material_flag": True,
            "catalyst_summary": "材料未確認",
        }

    combined = (text + " " + src).lower()

    category = "材料不明"
    if any(k in combined for k in ["決算", "上方修正", "通期", "業績", "earnings", "guidance"]):
        category = "決算/上方修正"
    elif any(k in combined for k in ["m&a", "tob", "買収", "acquisition", "merger"]):
        category = "M&A/TOB"
    elif any(k in combined for k in ["提携", "契約", "受注", "採用", "partnership", "deal", "contract"]):
        category = "大型契約/業務提携"
    elif any(k in combined for k in ["fda", "治験", "承認", "approval", "trial"]):
        category = "FDA/治験/承認"
    elif any(k in combined for k in ["政策", "国策", "補助金", "policy", "government"]):
        category = "政策/国策"
    elif any(k in combined for k in ["ai", "半導体", "電池", "宇宙", "防衛", "量子"]):
        category = "テーマ波及"
    elif any(k in combined for k in ["増配", "自社株買い", "buyback", "dividend"]):
        category = "増配/自社株買い"
    elif any(k in combined for k in ["上場廃止", "監理", "提出遅延", "going concern", "delist"]):
        category = "悪材料出尽くし"

    # 材料ソースランク
    if any(k in src.lower() for k in ["edgar", "sec", "tdnet", "jpx", "ir", "公式", "press release"]):
        source_rank = "一次"
    elif src:
        source_rank = "二次"
    else:
        source_rank = "なし"

    strength = 60.0 if source_rank == "一次" else (40.0 if source_rank == "二次" else 20.0)
    continuity = 50.0 if category in ("テーマ波及", "政策/国策", "大型契約/業務提携") else 30.0
    weak = (source_rank == "なし") or (category == "材料不明")

    return {
        "catalyst_category": category,
        "catalyst_timing": "T0前後" if src else "不明",
        "catalyst_strength_score": strength,
        "catalyst_continuity_score": continuity,
        "material_confirmed": source_rank in ("一次", "二次"),
        "material_source_rank": source_rank,
        "weak_material_flag": weak,
        "catalyst_summary": text or "材料未確認",
    }


# ===== T-1判定 =====
def judge_t1(features: Dict, setup: Dict, catalyst: Dict) -> Dict:
    """T-1時点で「入る余地」があったかを判定"""
    overext = features.get("t1_overextension_score") or 0
    vol_r = features.get("t1_volume_ratio_20d") or 0
    sup_dist = features.get("t1_support_distance") or 0
    res_up = features.get("t1_resistance_upside") or 0
    ma25_dev = features.get("t1_ma25_deviation") or 0
    pc_20 = features.get("t1_price_change_20d") or 0

    vol_type = setup.get("volume_type", "")
    chart_type = setup.get("chart_type", "")
    weak_mat = catalyst.get("weak_material_flag", False)
    cat_cat = catalyst.get("catalyst_category", "")

    # 除外系
    if cat_cat == "悪材料出尽くし" and not catalyst.get("material_confirmed", False):
        return {
            "t1_judgement": "イベント確認後のみ",
            "t1_entry_possible": "条件付き",
            "t1_entry_type": "イベント結果待ち",
        }

    if overext >= 70 or pc_20 >= 80:
        return {
            "t1_judgement": "見送り",
            "t1_entry_possible": "なし",
            "t1_entry_type": "上がり切り",
        }

    # ポジティブ系
    positive_signals = 0
    if vol_type in ("先行大商い", "売り枯れ", "価格維持", "再点火開始"):
        positive_signals += 1
    if chart_type in ("ブレイク前", "下ヒゲ反転", "初動後押し目", "値幅収縮"):
        positive_signals += 1
    if 0 < sup_dist < 15 and res_up >= 20:
        positive_signals += 1
    if ma25_dev < 30 and overext < 40:
        positive_signals += 1
    if catalyst.get("material_confirmed", False):
        positive_signals += 1

    if positive_signals >= 4 and not weak_mat:
        return {
            "t1_judgement": "入る余地あり",
            "t1_entry_possible": "あり",
            "t1_entry_type": "通常エントリー",
        }
    elif positive_signals >= 3:
        return {
            "t1_judgement": "条件付き",
            "t1_entry_possible": "条件付き",
            "t1_entry_type": "小ロット限定" if weak_mat else "通常エントリー(様子見)",
        }
    elif positive_signals >= 2 and vol_type in ("先行大商い", "売り枯れ"):
        return {
            "t1_judgement": "条件付き",
            "t1_entry_possible": "条件付き",
            "t1_entry_type": "翌寄り前気配確認のみ",
        }
    else:
        # T0で初めて出来高急増 → T0初動のみ型
        if vol_r < 1.2 and chart_type not in ("ブレイク前", "値幅収縮"):
            return {
                "t1_judgement": "T0初動のみ",
                "t1_entry_possible": "なし",
                "t1_entry_type": "事後検証のみ",
            }
        return {
            "t1_judgement": "見送り",
            "t1_entry_possible": "なし",
            "t1_entry_type": "事後検証のみ",
        }


def build_nlm_data(case: Dict) -> str:
    """NotebookLM 用 NLM_DATA 行を生成"""
    keys = [
        "symbol", "name", "market", "move_date", "move_percent",
        "catalyst_category", "catalyst_timing", "material_source_rank",
        "t1_judgement", "t1_entry_type", "setup_type", "volume_type", "chart_type",
        "t1_close", "t1_volume_ratio_20d", "t1_ma25_deviation",
        "t1_resistance_upside", "t1_support_distance", "t1_overextension_score",
        "t0_result_move_percent", "hit_20_percent",
    ]
    parts = []
    for k in keys:
        v = case.get(k)
        if v is None:
            parts.append(f"{k}=NA")
        elif isinstance(v, bool):
            parts.append(f"{k}={'1' if v else '0'}")
        elif isinstance(v, float):
            parts.append(f"{k}={v:.2f}")
        else:
            parts.append(f"{k}={v}")
    return "NLM_DATA|" + "|".join(parts)


# ===== メイン関数 =====
def analyze_surge_case(
    symbol: str,
    market: str,
    move_date: str,
    move_percent_user: Optional[float] = None,
    user_memo: Optional[str] = None,
    material_url: Optional[str] = None,
    catalyst_text: Optional[str] = None,
    news_source: Optional[str] = None,
    name: Optional[str] = None,
) -> Dict:
    """急騰銘柄を分析して構造化AARを返す"""
    yahoo_sym = _yahoo_symbol(symbol, market)
    df = _fetch_ohlcv(yahoo_sym, market, move_date)
    if df is None:
        return {
            "status": "failed",
            "error": f"OHLCV取得失敗 ({yahoo_sym})",
            "symbol": symbol,
            "yahoo_symbol": yahoo_sym,
            "market": market,
            "move_date": move_date,
        }

    t0_idx = _find_t0_index(df, move_date)
    if t0_idx is None or t0_idx < 5:
        return {
            "status": "failed",
            "error": f"T0インデックス特定失敗 (move_date={move_date}, df_range={df['date'].min()}-{df['date'].max()})",
            "symbol": symbol,
            "yahoo_symbol": yahoo_sym,
            "market": market,
            "move_date": move_date,
        }

    features = extract_t1_features(df, t0_idx)
    if "error" in features:
        return {"status": "failed", "error": features["error"], "symbol": symbol, "market": market, "move_date": move_date}

    labels = extract_t0_to_future_labels(df, t0_idx)
    t0_move = labels.get("t0_result_move_percent")

    setup = classify_setup(features, t0_move)
    catalyst = analyze_catalyst(catalyst_text, news_source)
    judgement = judge_t1(features, setup, catalyst)

    # OHLCV スナップショット (T-3, T-2, T-1, T0, T+1, T+3, T+5, T+10, T+20)
    snapshots = []
    for rel_label, offset in [("T-3", -3), ("T-2", -2), ("T-1", -1), ("T0", 0), ("T+1", 1), ("T+3", 3), ("T+5", 5), ("T+10", 10), ("T+20", 20)]:
        idx = t0_idx + offset
        if 0 <= idx < len(df):
            row = df.iloc[idx]
            snapshots.append({
                "relative_day": rel_label,
                "date": str(row["date"]),
                "open": _safe_float(row["open"]),
                "high": _safe_float(row["high"]),
                "low": _safe_float(row["low"]),
                "close": _safe_float(row["close"]),
                "volume": _safe_float(row["volume"]),
            })

    move_pct_calc = labels.get("t0_result_move_percent")

    # is_positive: T0以降に+20%達成 かつ 上がり切り型じゃない
    is_positive = bool(labels.get("hit_20_percent")) and setup.get("setup_type") != "上がり切り型"
    # is_negative: T0以降に+20%未達 または 上がり切り後ドローダウン大
    is_negative = (not labels.get("hit_20_percent")) or (
        (labels.get("t1_to_t20_max_drawdown") or 0) < -20
    )

    case = {
        "status": "ok",
        "symbol": symbol,
        "yahoo_symbol": yahoo_sym,
        "name": name or symbol,
        "market": market,
        "move_date": move_date,
        "move_percent_user": move_percent_user,
        "move_percent_calculated": move_pct_calc,
        "move_percent": move_pct_calc if move_pct_calc is not None else move_percent_user,
        "user_memo": user_memo,
        "material_url": material_url,
        # 特徴量 (T-1時点)
        "t1_close": features.get("t1_close"),
        "t1_volume": features.get("t1_volume"),
        "t1_volume_ratio_20d": features.get("t1_volume_ratio_20d"),
        "t2_volume_ratio_20d": features.get("t2_volume_ratio_20d"),
        "t3_volume_ratio_20d": features.get("t3_volume_ratio_20d"),
        "t1_price_change_1d": features.get("t1_price_change_1d"),
        "t1_price_change_3d": features.get("t1_price_change_3d"),
        "t1_price_change_5d": features.get("t1_price_change_5d"),
        "t1_price_change_20d": features.get("t1_price_change_20d"),
        "t1_ma5_deviation": features.get("t1_ma5_deviation"),
        "t1_ma25_deviation": features.get("t1_ma25_deviation"),
        "t1_support_distance": features.get("t1_support_distance"),
        "t1_resistance_upside": features.get("t1_resistance_upside"),
        "t1_range_break_flag": features.get("t1_range_break_flag"),
        "t1_high_close_flag": features.get("t1_high_close_flag"),
        "t1_lower_shadow_flag": features.get("t1_lower_shadow_flag"),
        "t1_upper_shadow_flag": features.get("t1_upper_shadow_flag"),
        "t1_overextension_score": features.get("t1_overextension_score"),
        # 材料
        **{k: v for k, v in catalyst.items() if k != "catalyst_summary"},
        "catalyst": catalyst.get("catalyst_summary"),
        # 分類
        **setup,
        # T-1判定
        **judgement,
        # T0以降ラベル
        **labels,
        # その他
        "is_positive_case": is_positive,
        "is_negative_case": is_negative,
        "snapshots": snapshots,
    }

    # NLM_DATA
    case["nlm_data"] = build_nlm_data(case)
    return case
