"""現在銘柄を T-1 相当の特徴量に変換し、AAR学習データと類似度マッチング"""
from typing import Dict, List, Optional
import math
import numpy as np

from app.services.aar_analyzer import extract_t1_features, classify_setup, analyze_catalyst, judge_t1
from app.services.price_fetcher import get_stock_data
from app.services import aar_db


# 距離計算 - 数値特徴の重み付きL1
NUMERIC_WEIGHTS = {
    "t1_volume_ratio_20d": 1.0,
    "t1_price_change_5d": 1.0,
    "t1_price_change_20d": 0.8,
    "t1_ma25_deviation": 1.0,
    "t1_support_distance": 0.6,
    "t1_resistance_upside": 1.0,
    "t1_overextension_score": 1.2,
}
NUMERIC_SCALES = {
    "t1_volume_ratio_20d": 3.0,
    "t1_price_change_5d": 30.0,
    "t1_price_change_20d": 50.0,
    "t1_ma25_deviation": 50.0,
    "t1_support_distance": 30.0,
    "t1_resistance_upside": 50.0,
    "t1_overextension_score": 100.0,
}


def _numeric_distance(a: Dict, b: Dict, weights: Optional[Dict[str, float]] = None) -> float:
    """重み付き正規化L1距離 (0=完全一致, 大きいほど離れる)。
    weights を渡せば動的重み (判別力に応じた強調) を使う。None なら静的 NUMERIC_WEIGHTS。
    """
    if weights is None:
        weights = NUMERIC_WEIGHTS
    total = 0.0
    weight_sum = 0.0
    for k, w in weights.items():
        va = a.get(k)
        vb = b.get(k)
        if va is None or vb is None:
            continue
        scale = NUMERIC_SCALES.get(k, 1.0)
        total += w * abs(float(va) - float(vb)) / scale
        weight_sum += w
    if weight_sum == 0:
        return 1.0
    return total / weight_sum


def compute_dynamic_weights() -> Dict[str, float]:
    """training_feature_vectors の positive/negative 平均値から
    各特徴量の判別力 (|pos_avg - neg_avg| / scale) を測り、
    NUMERIC_WEIGHTS の base に最大3倍の倍率を掛けて返す。
    判別力が高い特徴量ほど距離計算で重要視される。失敗時は静的重みにフォールバック。
    """
    try:
        from app.database import SessionLocal
        from sqlalchemy import func
        from app.models.models import TrainingFeatureVector as T
        pos_cts = ["positive_surge", "semi_positive_surge"]
        neg_cts = ["negative_non_surge", "failed_overextended",
                   "failed_weak_material", "failed_material_exhaustion", "failed_bad_news"]
        mapping = [
            ("t1_volume_ratio_20d", "volume_ratio_20d"),
            ("t1_price_change_5d", "price_change_5d"),
            ("t1_price_change_20d", "price_change_20d"),
            ("t1_ma25_deviation", "ma25_deviation"),
            ("t1_support_distance", "support_distance"),
            ("t1_resistance_upside", "resistance_upside"),
            ("t1_overextension_score", "overextension_score"),
        ]
        db = SessionLocal()
        try:
            new_w: Dict[str, float] = {}
            for tk, fld in mapping:
                col = getattr(T, fld, None)
                if col is None:
                    new_w[tk] = NUMERIC_WEIGHTS.get(tk, 1.0)
                    continue
                pa = db.query(func.avg(col)).filter(T.case_type.in_(pos_cts)).scalar() or 0
                na = db.query(func.avg(col)).filter(T.case_type.in_(neg_cts)).scalar() or 0
                scale = NUMERIC_SCALES.get(tk, 1.0)
                disc = min(1.0, abs(float(pa) - float(na)) / max(scale, 1e-6))
                base = NUMERIC_WEIGHTS.get(tk, 1.0)
                new_w[tk] = base * (1.0 + 2.0 * disc)
            return new_w
        finally:
            db.close()
    except Exception:
        return dict(NUMERIC_WEIGHTS)


def _categorical_match(a: Dict, b: Dict) -> int:
    """カテゴリ一致数"""
    match = 0
    for k in ("setup_type", "volume_type", "chart_type", "catalyst_category"):
        if a.get(k) and a.get(k) == b.get(k):
            match += 1
    return match


def compute_current_features(symbol: str, market: str) -> Dict:
    """現在銘柄の T-1 相当(=最新営業日)特徴量を計算"""
    df = get_stock_data(symbol, period="6mo", market=market)
    if df is None or len(df) < 10:
        return {"status": "failed", "error": "OHLCV取得失敗"}
    df = df.sort_values("date").reset_index(drop=True)
    # 最終行を「仮想T0」と見立て、T-1=最終行で extract_t1_features を呼ぶには
    # extract_t1_features(df, t0_idx) は t0_idx-1 を T-1 として処理するので、
    # ここでは「最新日 = T-1」相当として、仮想 t0_idx を len(df) にする
    virtual_t0 = len(df)
    # extract_t1_features は t0_idx - 1 を T-1 として処理する → 最新日が T-1 になる
    feats = extract_t1_features(df, virtual_t0)
    if "error" in feats:
        return {"status": "failed", "error": feats["error"]}

    # 仮の catalyst (現在銘柄は材料情報未取得 → 不明)
    catalyst = analyze_catalyst(None, None)
    setup = classify_setup(feats, None)
    judgement = judge_t1(feats, setup, catalyst)

    feats.update(catalyst)
    feats.update(setup)
    feats.update(judgement)
    feats["status"] = "ok"
    feats["symbol"] = symbol
    feats["market"] = market
    return feats


def match_against_library(current: Dict, library: List[Dict], top_k: int = 5) -> Dict:
    """現在銘柄を学習データ全件と比較"""
    if not library:
        return {
            "prediction_label": "学習データ不足",
            "entry_timing_type": "判定不能",
            "final_prediction_score": 0,
            "positive_case_similarity": 0,
            "negative_case_similarity": 0,
            "matched_cases": [],
            "reason_summary": "AAR学習データがまだありません",
        }

    scored = []
    for case in library:
        dist = _numeric_distance(current, case)
        cat_match = _categorical_match(current, case)
        # similarity = 1 - dist + cat_match * 0.15 (重み付き)
        similarity = max(0.0, 1.0 - dist) + 0.15 * cat_match
        case_score = {
            "case_id": case.get("case_id"),
            "symbol": case.get("symbol"),
            "move_date": case.get("move_date"),
            "is_positive": case.get("is_positive"),
            "is_negative": case.get("is_negative"),
            "setup_type": case.get("setup_type"),
            "catalyst_category": case.get("catalyst_category"),
            "t1_judgement": case.get("t1_judgement"),
            "similarity": round(similarity, 4),
            "hit_20_percent": case.get("hit_20_percent"),
        }
        scored.append(case_score)

    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top = scored[:top_k]

    # ポジティブ/ネガティブ集計
    pos_sims = [c["similarity"] for c in top if c.get("is_positive")]
    neg_sims = [c["similarity"] for c in top if c.get("is_negative")]
    t0_only_sims = [c["similarity"] for c in top if c.get("t1_judgement") == "T0初動のみ"]
    overext_sims = [c["similarity"] for c in top if "上がり切り" in (c.get("setup_type") or "")]

    pos_score = sum(pos_sims) / max(1, len(pos_sims)) if pos_sims else 0
    neg_score = sum(neg_sims) / max(1, len(neg_sims)) if neg_sims else 0
    t0_only_score = sum(t0_only_sims) / max(1, len(t0_only_sims)) if t0_only_sims else 0
    overext_score = sum(overext_sims) / max(1, len(overext_sims)) if overext_sims else 0

    # ランキング分類
    overext_current = current.get("t1_overextension_score") or 0
    pc_5 = current.get("t1_price_change_5d") or 0
    pc_20 = current.get("t1_price_change_20d") or 0
    weak_mat = current.get("weak_material_flag", True)
    cat_cat = current.get("catalyst_category", "材料不明")
    t1_judg = current.get("t1_judgement", "見送り")
    vol_type = current.get("volume_type", "")
    chart_type = current.get("chart_type", "")

    # 上がり切り警戒
    if overext_current >= 60 or pc_20 >= 80 or pc_5 >= 30:
        label = "上がり切り警戒"
        timing = "押し目待ち"
    elif cat_cat == "悪材料出尽くし":
        label = "悪材料出尽くし監視"
        timing = "イベント結果待ち"
    elif t1_judg == "T0初動のみ" or t0_only_score > 0.7:
        label = "T0後追い警戒"
        timing = "事後検証のみ"
    elif t1_judg == "入る余地あり" and pos_score > 0.5 and neg_score < pos_score:
        label = "急騰前夜候補"
        timing = "T-1〜寄り前判断"
    elif t1_judg == "条件付き" and pos_score > 0.3:
        label = "条件付き候補"
        timing = "小ロット限定"
    elif weak_mat and (vol_type in ("先行大商い", "再点火開始") or chart_type in ("ブレイク前", "値幅収縮")):
        label = "需給監視"
        timing = "材料発生待ち"
    elif cat_cat in ("テーマ波及", "政策/国策"):
        label = "テーマ監視"
        timing = "本命特定待ち"
    elif t1_judg == "見送り":
        label = "除外"
        timing = "対象外"
    else:
        label = "二段目監視"
        timing = "押し目待ち"

    # final_prediction_score (0-100)
    final = 50.0 + (pos_score - neg_score) * 40 - overext_score * 10 - t0_only_score * 15
    if weak_mat:
        final -= 10
    if overext_current >= 60:
        final -= 15
    final = max(0.0, min(100.0, final))

    reason_bits = []
    if pos_score > 0.5:
        reason_bits.append(f"ポジティブ類似 {pos_score:.2f}")
    if neg_score > 0.5:
        reason_bits.append(f"ネガティブ類似 {neg_score:.2f}")
    if t0_only_score > 0.5:
        reason_bits.append(f"T0初動のみ類似 {t0_only_score:.2f}")
    if overext_current >= 60:
        reason_bits.append(f"上がり切りリスク {overext_current:.0f}")
    if weak_mat:
        reason_bits.append("材料未確認")
    reason_summary = " / ".join(reason_bits) if reason_bits else "標準パターン"

    return {
        "prediction_label": label,
        "entry_timing_type": timing,
        "final_prediction_score": round(final, 1),
        "positive_case_similarity": round(pos_score, 4),
        "negative_case_similarity": round(neg_score, 4),
        "t0_only_similarity": round(t0_only_score, 4),
        "overextension_similarity": round(overext_score, 4),
        "matched_cases": top,
        "reason_summary": reason_summary,
        "t1_entry_possible_estimate": current.get("t1_entry_possible"),
        "t1_judgement": t1_judg,
        "setup_type": current.get("setup_type"),
        "volume_type": vol_type,
        "chart_type": chart_type,
        "catalyst_category": cat_cat,
        "overextension_risk_score": overext_current,
        "catalyst_quality_score": current.get("catalyst_strength_score") or 0,
        "catalyst_continuity_score": current.get("catalyst_continuity_score") or 0,
        "weak_material_flag": weak_mat,
    }


def predict_symbol(symbol: str, market: str) -> Dict:
    """1銘柄の予測パイプライン"""
    current = compute_current_features(symbol, market)
    if current.get("status") != "ok":
        return {"status": "failed", "symbol": symbol, "error": current.get("error")}

    library = aar_db.get_feature_vectors_for_matching(limit=2000)
    pred = match_against_library(current, library, top_k=5)
    pred["status"] = "ok"
    pred["symbol"] = symbol
    pred["market"] = market

    # 過去5年training_feature_vectorとの類似度も計算
    try:
        from app.services.training_builder import get_training_features_for_matching
        tlibrary = get_training_features_for_matching(limit=2000).get("items", [])
        if tlibrary:
            hist = _match_training_library(current, tlibrary, top_k=5)
            pred.update(hist)
    except Exception as e:
        print(f"training match failed: {e}")
    return pred


def _match_training_library(current: Dict, library: List[Dict], top_k: int = 5) -> Dict:
    """過去5年training_feature_vector との類似度マッチ"""
    if not library:
        return {
            "historical_positive_similarity": 0,
            "historical_negative_similarity": 0,
            "overextended_failure_similarity": 0,
            "weak_material_failure_similarity": 0,
            "material_exhaustion_failure_similarity": 0,
            "similar_historical_cases": [],
            "failure_similarity_type": None,
            "training_based_score_adjustment": 0,
        }

    scored = []
    for c in library:
        dist = _numeric_distance(current, c)
        similarity = max(0.0, 1.0 - dist)
        scored.append({"case": c, "similarity": similarity})
    scored.sort(key=lambda x: x["similarity"], reverse=True)
    top = scored[:top_k]

    def avg(items, predicate):
        sims = [x["similarity"] for x in items if predicate(x["case"])]
        return round(sum(sims) / max(1, len(sims)), 4) if sims else 0.0

    positives = avg(scored[:30], lambda c: c.get("case_type") in ("positive_surge", "semi_positive_surge"))
    negatives = avg(scored[:30], lambda c: c.get("case_type") and c.get("case_type").startswith(("negative_", "failed_")))
    overext = avg(scored[:30], lambda c: c.get("case_type") == "failed_overextended")
    weak = avg(scored[:30], lambda c: c.get("case_type") == "failed_weak_material")
    exh = avg(scored[:30], lambda c: c.get("case_type") == "failed_material_exhaustion")
    bad = avg(scored[:30], lambda c: c.get("case_type") == "failed_bad_news")

    # 最も似ている失敗タイプ
    fail_map = {"overextended": overext, "weak_material": weak, "material_exhaustion": exh, "bad_news": bad}
    fail_type = max(fail_map.items(), key=lambda x: x[1])
    failure_type = fail_type[0] if fail_type[1] >= 0.3 else None

    adj = round((positives - negatives) * 30, 1)
    # ペナルティ系
    if overext >= 0.5: adj -= 10
    if weak >= 0.5: adj -= 5
    if exh >= 0.5: adj -= 10

    return {
        "historical_positive_similarity": positives,
        "historical_negative_similarity": negatives,
        "overextended_failure_similarity": overext,
        "weak_material_failure_similarity": weak,
        "material_exhaustion_failure_similarity": exh,
        "bad_news_failure_similarity": bad,
        "similar_historical_cases": [{
            "symbol": x["case"].get("symbol"),
            "case_type": x["case"].get("case_type"),
            "label_hit_20_percent": x["case"].get("label_hit_20_percent"),
            "label_max_gain_20d": x["case"].get("label_max_gain_20d"),
            "similarity": round(x["similarity"], 4),
        } for x in top],
        "failure_similarity_type": failure_type,
        "training_based_score_adjustment": adj,
    }
