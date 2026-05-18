"""AI材料調査エンジン

ユーザー入力URL・テキストをまず分析し、続いて簡易的にYahoo Finance/RSS等から
ニュースタイトルを引いて分類する。LLM_API_KEY があれば要約呼び出しを行う hook あり。
"""
import os
import re
from typing import Dict, List, Optional
from datetime import datetime, timezone
import hashlib

import requests


CATALYST_KEYWORDS = {
    "決算": ["決算", "earnings", "業績", "quarterly report"],
    "上方修正": ["上方修正", "guidance raised", "raised guidance", "業績修正"],
    "増配": ["増配", "dividend", "配当"],
    "自社株買い": ["自社株買", "buyback", "share repurchase"],
    "M&A": ["m&a", "merger", "買収", "acquisition"],
    "TOB": ["tob", "tender offer", "公開買付"],
    "MBO": ["mbo", "management buyout"],
    "業務提携": ["提携", "partnership", "alliance"],
    "大型契約": ["契約", "契約締結", "受注", "contract", "deal"],
    "FDA/治験/承認": ["fda", "治験", "承認", "trial", "approval", "phase iii", "phase 3"],
    "政策/国策": ["政策", "国策", "補助金", "policy", "government", "規制緩和"],
    "テーマ波及": ["ai", "半導体", "データセンター", "電力", "防衛", "宇宙", "量子", "暗号資産"],
    "悪材料出尽くし": ["上場廃止", "監理", "提出遅延", "going concern", "delist", "希薄化"],
}

RISK_KEYWORDS = {
    "bad_news_unresolved_flag": ["継続企業の前提", "going concern", "監理", "提出遅延", "上場廃止リスク"],
    "dilution_risk_flag": ["希薄化", "新株発行", "公募", "dilution", "secondary offering"],
    "going_concern_risk_flag": ["継続企業", "going concern"],
    "delisting_risk_flag": ["上場廃止", "delisting"],
}


SOURCE_RANK_MAP = {
    "tdnet": "一次", "edinet": "一次", "edgar": "一次",
    "ir": "一次", "press": "一次", "公式": "一次",
    "company": "一次",
    "reuters": "二次", "bloomberg": "二次", "nikkei": "二次",
    "yahoo": "三次", "news": "三次",
    "twitter": "SNS", "x.com": "SNS", "5ch": "SNS", "ヤフー掲示板": "SNS",
}


def _classify_text(text: str) -> Dict:
    """テキスト本文から材料カテゴリ・リスクフラグを抽出"""
    if not text:
        return {
            "catalyst_category": "材料不明",
            "matched_keywords": [],
            "risk_flags": {},
        }
    text_lower = text.lower()
    matched = {}
    for cat, kws in CATALYST_KEYWORDS.items():
        hits = [k for k in kws if k in text_lower or k in text]
        if hits:
            matched[cat] = len(hits)

    category = "材料不明"
    if matched:
        # 最も多くマッチしたカテゴリ
        category = max(matched.items(), key=lambda x: x[1])[0]

    risk_flags = {}
    for flag, kws in RISK_KEYWORDS.items():
        if any(k in text_lower or k in text for k in kws):
            risk_flags[flag] = True

    return {
        "catalyst_category": category,
        "matched_keywords": list(matched.keys()),
        "risk_flags": risk_flags,
    }


def _classify_url(url: str) -> Dict:
    """URLからソースタイプとランクを判定"""
    if not url:
        return {"source_type": "unknown", "source_rank": "なし"}
    url_lower = url.lower()
    source_type = "general"
    source_rank = "三次"
    for key, rank in SOURCE_RANK_MAP.items():
        if key in url_lower:
            source_type = key
            source_rank = rank
            break

    # 一次ソースの特殊判定
    if "tdnet" in url_lower or "release.tdnet" in url_lower:
        source_type = "tdnet"
        source_rank = "一次"
    elif "edinet" in url_lower:
        source_type = "edinet"
        source_rank = "一次"
    elif "sec.gov" in url_lower or "edgar" in url_lower:
        source_type = "edgar"
        source_rank = "一次"

    return {"source_type": source_type, "source_rank": source_rank}


def _fetch_url(url: str) -> Optional[str]:
    """URLからテキストを取得 (簡易、html parsing最低限)"""
    if not url:
        return None
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0)"}, timeout=15)
        if r.status_code != 200:
            return None
        # HTMLタグを軽く除去
        text = re.sub(r"<script.*?</script>", "", r.text, flags=re.DOTALL)
        text = re.sub(r"<style.*?</style>", "", text, flags=re.DOTALL)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text[:5000]
    except Exception as e:
        print(f"material URL fetch failed: {e}")
        return None


def _llm_summarize(text: str, symbol: str) -> Optional[str]:
    """LLM_API_KEYがあれば要約。今は hook のみ"""
    api_key = os.getenv("LLM_API_KEY")
    if not api_key or not text:
        return None
    # ここに OpenAI/Anthropic/Gemini クライアントを呼ぶ実装を入れる予定
    # MVP では未実装のため None
    return None


def research_material(
    symbol: str,
    market: str = "JP",
    user_text: Optional[str] = None,
    urls: Optional[List[str]] = None,
) -> Dict:
    """材料調査のメイン関数"""
    urls = urls or []
    all_text_bits = []
    source_meta = []

    if user_text:
        all_text_bits.append(user_text)
        source_meta.append({"source_type": "user_input", "source_rank": "ユーザー入力", "url": None})

    for url in urls:
        cls_url = _classify_url(url)
        text = _fetch_url(url)
        if text:
            all_text_bits.append(text)
            source_meta.append({"url": url, "source_type": cls_url["source_type"], "source_rank": cls_url["source_rank"]})

    combined = "\n".join(all_text_bits)
    classification = _classify_text(combined)

    # ソースランクの最高位を採用
    rank_priority = {"一次": 4, "二次": 3, "三次": 2, "ユーザー入力": 1, "SNS": 1, "なし": 0}
    best_source = max(source_meta, key=lambda s: rank_priority.get(s["source_rank"], 0), default={"source_rank": "なし", "source_type": "none", "url": None})

    found = bool(combined.strip())
    confirmed = best_source["source_rank"] in ("一次", "二次")

    # スコア算出
    category = classification["catalyst_category"]
    has_keywords = bool(classification["matched_keywords"])
    risk_flags = classification["risk_flags"]

    rank_score = {"一次": 80, "二次": 55, "三次": 30, "ユーザー入力": 25, "SNS": 10, "なし": 0}.get(best_source["source_rank"], 0)
    keyword_bonus = 15 if has_keywords else 0
    catalyst_quality = min(100, rank_score + keyword_bonus)

    # 継続性: テーマ系・政策系は高め
    if category in ("テーマ波及", "政策/国策", "FDA/治験/承認", "大型契約"):
        catalyst_continuity = 60
    elif category in ("決算", "上方修正"):
        catalyst_continuity = 45
    elif category in ("M&A", "TOB"):
        catalyst_continuity = 70  # M&Aは終わるまで残る
    else:
        catalyst_continuity = 25

    # 鮮度
    catalyst_freshness = 70 if found and confirmed else (40 if found else 10)

    # サプライズ度
    if "上方修正" in combined or "大幅" in combined or "approval" in combined.lower():
        catalyst_surprise = 70
    elif has_keywords:
        catalyst_surprise = 40
    else:
        catalyst_surprise = 15

    # テーマ追い風
    theme_tailwind = 60 if category == "テーマ波及" or "政策" in category else 20

    # 出尽くしリスク
    exhaustion = 0
    if "出尽くし" in combined or "材料出" in combined:
        exhaustion = 60
    if found and category in ("M&A", "TOB", "MBO") and "完了" in combined:
        exhaustion = 80
    material_exhaustion = exhaustion

    weak_material = (not confirmed) or (category == "材料不明" and not has_keywords)

    return {
        "symbol": symbol,
        "market": market,
        "material_found": found,
        "material_confirmed": confirmed,
        "material_source_url": best_source["url"],
        "material_source_type": best_source["source_type"],
        "material_source_rank": best_source["source_rank"],
        "material_published_at": None,  # 抽出未実装
        "material_timing": "T-1までに観測可" if confirmed else "不明",
        "catalyst_category": category,
        "catalyst_quality_score": catalyst_quality,
        "catalyst_continuity_score": catalyst_continuity,
        "catalyst_freshness_score": catalyst_freshness,
        "catalyst_surprise_score": catalyst_surprise,
        "theme_tailwind_score": theme_tailwind,
        "material_exhaustion_risk_score": material_exhaustion,
        "bad_news_unresolved_flag": bool(risk_flags.get("bad_news_unresolved_flag")),
        "dilution_risk_flag": bool(risk_flags.get("dilution_risk_flag")),
        "going_concern_risk_flag": bool(risk_flags.get("going_concern_risk_flag")),
        "delisting_risk_flag": bool(risk_flags.get("delisting_risk_flag")),
        "matched_keywords": classification["matched_keywords"],
        "weak_material_flag": weak_material,
        "title": (user_text or "").split("\n")[0][:200] if user_text else None,
        "summary": (combined[:500] if combined else "材料未確認"),
        "ai_analysis": _llm_summarize(combined, symbol) or "(LLM未設定、ルールベース分類のみ)",
        "sources": source_meta,
    }
