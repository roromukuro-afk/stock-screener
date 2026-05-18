"""pattern_library に初期パターン12種をseed投入"""
from typing import List, Dict
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.models import PatternLibrary


PATTERNS: List[Dict] = [
    {
        "pattern_name": "前夜IR確認型",
        "pattern_category": "急騰前夜候補",
        "description": "T-1引け後または翌寄り前に公式IR/開示が出るが、T-1までに先行出来高または材料の予兆が既に出ているケース",
        "required_conditions": ["material_confirmed:true", "catalyst_strength_score>=40"],
        "positive_conditions": ["volume_type:先行大商い", "chart_type:ブレイク前", "t1_resistance_upside>=20"],
        "negative_conditions": ["overextension_score>=60", "t1_price_change_20d>=80"],
        "exclusion_conditions": ["stale_price", "instrument_type:etf"],
        "confidence_weight": 1.2,
    },
    {
        "pattern_name": "決算サプライズ先回り型",
        "pattern_category": "急騰前夜候補",
        "description": "決算発表前後に先行出来高 + 上方修正観測。T-1で既に出来高2倍以上",
        "required_conditions": ["catalyst_category:決算/上方修正"],
        "positive_conditions": ["t1_volume_ratio_20d>=2.0", "t1_high_close_flag:true"],
        "negative_conditions": ["t1_overextension_score>=70"],
        "exclusion_conditions": ["t1_price_change_5d>=30"],
        "confidence_weight": 1.1,
    },
    {
        "pattern_name": "テーマ波及+小型需給型",
        "pattern_category": "条件付き候補",
        "description": "テーマ波及で同業物色、小型株の需給軽さで反応するパターン。会社固有材料は弱い",
        "required_conditions": ["catalyst_category:テーマ波及"],
        "positive_conditions": ["t1_volume_ratio_20d>=1.5", "t1_resistance_upside>=20"],
        "negative_conditions": ["weak_material_flag:true", "overextension_score>=50"],
        "exclusion_conditions": [],
        "confidence_weight": 0.7,
    },
    {
        "pattern_name": "売り枯れ後の再点火型",
        "pattern_category": "急騰前夜候補",
        "description": "出来高が枯渇した後、安値切り上げや下ヒゲ反転で再点火開始",
        "required_conditions": ["volume_type:売り枯れ OR volume_type:再点火開始"],
        "positive_conditions": ["chart_type:下ヒゲ反転 OR chart_type:値幅収縮", "t1_support_distance<15"],
        "negative_conditions": ["t1_price_change_20d<-30"],
        "exclusion_conditions": ["instrument_type:warrant", "instrument_type:unit"],
        "confidence_weight": 1.0,
    },
    {
        "pattern_name": "ブレイク初動型",
        "pattern_category": "急騰前夜候補",
        "description": "20日レンジ上限ブレイク後の高値引け。出来高は通常〜やや先行",
        "required_conditions": ["t1_range_break_flag:true", "t1_high_close_flag:true"],
        "positive_conditions": ["t1_volume_ratio_20d>=1.3"],
        "negative_conditions": ["overextension_score>=60"],
        "exclusion_conditions": ["t1_price_change_5d>=40"],
        "confidence_weight": 1.05,
    },
    {
        "pattern_name": "悪材料出尽くし型",
        "pattern_category": "悪材料出尽くし監視",
        "description": "監理銘柄解除/レビュー結論/債務超過解消/FDA結果等の公式リスク後退",
        "required_conditions": ["catalyst_category:悪材料出尽くし", "material_confirmed:true"],
        "positive_conditions": ["t1_volume_ratio_20d>=2.0"],
        "negative_conditions": ["material_confirmed:false"],
        "exclusion_conditions": [],
        "confidence_weight": 0.9,
    },
    {
        "pattern_name": "二段目モメンタム型",
        "pattern_category": "二段目監視",
        "description": "一段目急騰後の押し目→再ブレイク。一段目から押し目を作っており上がり切っていないこと",
        "required_conditions": ["t1_price_change_20d>=20", "t1_price_change_20d<60"],
        "positive_conditions": ["chart_type:初動後押し目", "t1_resistance_upside>=15"],
        "negative_conditions": ["t1_ma25_deviation>=40"],
        "exclusion_conditions": [],
        "confidence_weight": 0.85,
    },
    {
        "pattern_name": "T0初動のみ型",
        "pattern_category": "T0後追い警戒",
        "description": "T-1までに兆候がなく、T0で初めて出来高急増・大陽線。後追い禁止教師ラベル",
        "required_conditions": ["t0_only_flag:true"],
        "positive_conditions": [],
        "negative_conditions": ["t1_volume_ratio_20d<1.2"],
        "exclusion_conditions": ["entry_after_T0"],
        "confidence_weight": 0.5,
    },
    {
        "pattern_name": "上がり切り型",
        "pattern_category": "上がり切り警戒",
        "description": "25MA乖離50%以上または20日2倍以上。新規買い禁止、押し目待ち",
        "required_conditions": ["overextension_score>=70 OR t1_price_change_20d>=80"],
        "positive_conditions": [],
        "negative_conditions": ["all"],
        "exclusion_conditions": ["new_entry"],
        "confidence_weight": 0.0,
    },
    {
        "pattern_name": "材料弱い需給だけ型",
        "pattern_category": "需給監視",
        "description": "出来高は伸びるが会社固有材料なし。需給だけで動いている状態",
        "required_conditions": ["weak_material_flag:true", "t1_volume_ratio_20d>=1.5"],
        "positive_conditions": [],
        "negative_conditions": ["catalyst_strength_score>=40"],
        "exclusion_conditions": [],
        "confidence_weight": 0.4,
    },
    {
        "pattern_name": "悪材料ギャンブル型",
        "pattern_category": "イベント監視",
        "description": "未解消の悪材料がある状態で結果イベント待ち(FDA・訴訟・継続企業疑義など)",
        "required_conditions": ["bad_news_unresolved_flag:true"],
        "positive_conditions": [],
        "negative_conditions": [],
        "exclusion_conditions": ["normal_ranking"],
        "confidence_weight": 0.3,
    },
    {
        "pattern_name": "材料出尽くし型",
        "pattern_category": "材料出尽くし警戒",
        "description": "材料発表で急騰したが、続報がなく材料寿命切れ。二段ロケット不発",
        "required_conditions": ["t1_price_change_5d>=30", "catalyst_continuity_score<40"],
        "positive_conditions": [],
        "negative_conditions": [],
        "exclusion_conditions": [],
        "confidence_weight": 0.3,
    },
]


def seed_patterns() -> int:
    db: Session = SessionLocal()
    try:
        count = 0
        for p in PATTERNS:
            existing = db.query(PatternLibrary).filter(PatternLibrary.pattern_name == p["pattern_name"]).first()
            if existing:
                # 更新
                existing.pattern_category = p["pattern_category"]
                existing.description = p["description"]
                existing.required_conditions = p["required_conditions"]
                existing.positive_conditions = p["positive_conditions"]
                existing.negative_conditions = p["negative_conditions"]
                existing.exclusion_conditions = p["exclusion_conditions"]
                existing.confidence_weight = p["confidence_weight"]
            else:
                row = PatternLibrary(**p)
                db.add(row)
                count += 1
        db.commit()
        total = db.query(PatternLibrary).count()
        return total
    finally:
        db.close()
