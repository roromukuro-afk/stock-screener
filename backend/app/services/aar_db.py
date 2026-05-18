"""AAR学習データ DB永続化"""
from typing import List, Dict, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import SessionLocal
from app.models.models import (
    AARInputCase, AARAnalysisCase, AAROHLCVSnapshot, AARFeatureVector,
)


def save_input_case(symbol: str, market: str, move_date: str, **kwargs) -> int:
    db: Session = SessionLocal()
    try:
        row = AARInputCase(
            symbol=symbol,
            yahoo_symbol=kwargs.get("yahoo_symbol", symbol),
            name=kwargs.get("name"),
            market=market,
            move_date=move_date,
            move_percent_user=kwargs.get("move_percent_user"),
            user_memo=kwargs.get("user_memo"),
            material_url=kwargs.get("material_url"),
            source_file=kwargs.get("source_file"),
            status="pending",
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def save_analysis_case(input_case_id: int, case: Dict) -> int:
    """AAR分析結果をDB保存"""
    db: Session = SessionLocal()
    try:
        # 既存ケース重複チェック (同一symbol+move_date)
        existing = (db.query(AARAnalysisCase)
                    .filter(AARAnalysisCase.symbol == case["symbol"])
                    .filter(AARAnalysisCase.move_date == case["move_date"])
                    .first())
        if existing:
            # 上書き
            existing.move_percent = case.get("move_percent")
            existing.catalyst = case.get("catalyst")
            existing.catalyst_category = case.get("catalyst_category")
            existing.t1_judgement = case.get("t1_judgement")
            existing.setup_type = case.get("setup_type")
            existing.volume_type = case.get("volume_type")
            existing.chart_type = case.get("chart_type")
            existing.is_positive_case = case.get("is_positive_case", False)
            existing.is_negative_case = case.get("is_negative_case", False)
            existing.nlm_data_raw = case.get("nlm_data")
            db.commit()
            return existing.id

        row = AARAnalysisCase(
            input_case_id=input_case_id,
            symbol=case.get("symbol"),
            yahoo_symbol=case.get("yahoo_symbol"),
            name=case.get("name"),
            market=case.get("market"),
            move_date=case.get("move_date"),
            move_percent=case.get("move_percent"),
            catalyst=case.get("catalyst"),
            catalyst_category=case.get("catalyst_category"),
            catalyst_timing=case.get("catalyst_timing"),
            catalyst_strength_score=case.get("catalyst_strength_score"),
            catalyst_continuity_score=case.get("catalyst_continuity_score"),
            material_confirmed=case.get("material_confirmed", False),
            material_source_rank=case.get("material_source_rank"),
            t1_judgement=case.get("t1_judgement"),
            t1_entry_possible=case.get("t1_entry_possible"),
            t1_entry_type=case.get("t1_entry_type"),
            setup_type=case.get("setup_type"),
            volume_type=case.get("volume_type"),
            chart_type=case.get("chart_type"),
            overextension_risk_score=case.get("t1_overextension_score"),
            weak_material_flag=case.get("weak_material_flag", False),
            t0_only_flag=(case.get("t1_judgement") == "T0初動のみ"),
            already_ran_flag=(case.get("t1_overextension_score") or 0) >= 70,
            tags=case.get("tags") or [],
            nlm_data_raw=case.get("nlm_data"),
            is_positive_case=case.get("is_positive_case", False),
            is_negative_case=case.get("is_negative_case", False),
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def save_feature_vector(case_id: int, case: Dict) -> int:
    db: Session = SessionLocal()
    try:
        existing = db.query(AARFeatureVector).filter(AARFeatureVector.case_id == case_id).first()
        # T-1 date = first snapshot with relative_day=T-1
        t1_date = None
        for snap in case.get("snapshots", []):
            if snap.get("relative_day") == "T-1":
                t1_date = snap.get("date")
                break

        data = dict(
            case_id=case_id,
            symbol=case.get("symbol"),
            move_date=case.get("move_date"),
            feature_asof_date=t1_date,
            t1_close=case.get("t1_close"),
            t1_volume=case.get("t1_volume"),
            t1_volume_ratio_20d=case.get("t1_volume_ratio_20d"),
            t2_volume_ratio_20d=case.get("t2_volume_ratio_20d"),
            t3_volume_ratio_20d=case.get("t3_volume_ratio_20d"),
            t1_price_change_1d=case.get("t1_price_change_1d"),
            t1_price_change_3d=case.get("t1_price_change_3d"),
            t1_price_change_5d=case.get("t1_price_change_5d"),
            t1_price_change_20d=case.get("t1_price_change_20d"),
            t1_ma5_deviation=case.get("t1_ma5_deviation"),
            t1_ma25_deviation=case.get("t1_ma25_deviation"),
            t1_support_distance=case.get("t1_support_distance"),
            t1_resistance_upside=case.get("t1_resistance_upside"),
            t1_range_break_flag=case.get("t1_range_break_flag"),
            t1_high_close_flag=case.get("t1_high_close_flag"),
            t1_lower_shadow_flag=case.get("t1_lower_shadow_flag"),
            t1_upper_shadow_flag=case.get("t1_upper_shadow_flag"),
            t1_overextension_score=case.get("t1_overextension_score"),
            t1_fresh_material_flag=case.get("material_confirmed", False),
            t1_unknown_material_flag=(case.get("catalyst_category") == "材料不明"),
            t0_result_move_percent=case.get("t0_result_move_percent"),
            t1_to_t5_max_gain=case.get("t1_to_t5_max_gain"),
            t1_to_t20_max_gain=case.get("t1_to_t20_max_gain"),
            t1_to_t20_max_drawdown=case.get("t1_to_t20_max_drawdown"),
            hit_20_percent=case.get("hit_20_percent"),
        )
        if existing:
            for k, v in data.items():
                if k not in ("case_id",):
                    setattr(existing, k, v)
            db.commit()
            return existing.id
        row = AARFeatureVector(**data)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def save_snapshots(case_id: int, symbol: str, snapshots: List[Dict]):
    db: Session = SessionLocal()
    try:
        # 既存削除
        db.query(AAROHLCVSnapshot).filter(AAROHLCVSnapshot.case_id == case_id).delete()
        for snap in snapshots:
            row = AAROHLCVSnapshot(
                case_id=case_id,
                symbol=symbol,
                date=snap.get("date"),
                relative_day=snap.get("relative_day"),
                open=snap.get("open"),
                high=snap.get("high"),
                low=snap.get("low"),
                close=snap.get("close"),
                volume=snap.get("volume"),
            )
            db.add(row)
        db.commit()
    finally:
        db.close()


def update_input_status(input_case_id: int, status: str, error: str = None):
    db: Session = SessionLocal()
    try:
        row = db.query(AARInputCase).filter(AARInputCase.id == input_case_id).first()
        if row:
            row.status = status
            if error:
                row.error_message = error
            db.commit()
    finally:
        db.close()


def list_analysis_cases(limit: int = 200, offset: int = 0, filter_judgement: str = None) -> Dict:
    db: Session = SessionLocal()
    try:
        q = db.query(AARAnalysisCase)
        if filter_judgement:
            q = q.filter(AARAnalysisCase.t1_judgement == filter_judgement)
        total = q.count()
        rows = q.order_by(AARAnalysisCase.id.desc()).limit(limit).offset(offset).all()
        items = []
        for r in rows:
            items.append({
                "id": r.id,
                "symbol": r.symbol,
                "yahoo_symbol": r.yahoo_symbol,
                "name": r.name,
                "market": r.market,
                "move_date": r.move_date,
                "move_percent": r.move_percent,
                "catalyst_category": r.catalyst_category,
                "catalyst_timing": r.catalyst_timing,
                "catalyst_strength_score": r.catalyst_strength_score,
                "catalyst_continuity_score": r.catalyst_continuity_score,
                "material_confirmed": r.material_confirmed,
                "t1_judgement": r.t1_judgement,
                "t1_entry_type": r.t1_entry_type,
                "setup_type": r.setup_type,
                "volume_type": r.volume_type,
                "chart_type": r.chart_type,
                "overextension_risk_score": r.overextension_risk_score,
                "weak_material_flag": r.weak_material_flag,
                "t0_only_flag": r.t0_only_flag,
                "already_ran_flag": r.already_ran_flag,
                "is_positive_case": r.is_positive_case,
                "is_negative_case": r.is_negative_case,
                "tags": r.tags,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            })
        return {"total": total, "items": items, "limit": limit, "offset": offset}
    finally:
        db.close()


def get_aar_summary() -> Dict:
    db: Session = SessionLocal()
    try:
        total = db.query(AARAnalysisCase).count()
        positive = db.query(AARAnalysisCase).filter(AARAnalysisCase.is_positive_case == True).count()
        negative = db.query(AARAnalysisCase).filter(AARAnalysisCase.is_negative_case == True).count()
        by_judgement = dict(db.query(AARAnalysisCase.t1_judgement, func.count(AARAnalysisCase.id)).group_by(AARAnalysisCase.t1_judgement).all())
        by_catalyst = dict(db.query(AARAnalysisCase.catalyst_category, func.count(AARAnalysisCase.id)).group_by(AARAnalysisCase.catalyst_category).all())
        by_setup = dict(db.query(AARAnalysisCase.setup_type, func.count(AARAnalysisCase.id)).group_by(AARAnalysisCase.setup_type).all())
        by_volume = dict(db.query(AARAnalysisCase.volume_type, func.count(AARAnalysisCase.id)).group_by(AARAnalysisCase.volume_type).all())
        by_chart = dict(db.query(AARAnalysisCase.chart_type, func.count(AARAnalysisCase.id)).group_by(AARAnalysisCase.chart_type).all())
        t0_only = db.query(AARAnalysisCase).filter(AARAnalysisCase.t0_only_flag == True).count()
        already_ran = db.query(AARAnalysisCase).filter(AARAnalysisCase.already_ran_flag == True).count()
        weak_mat = db.query(AARAnalysisCase).filter(AARAnalysisCase.weak_material_flag == True).count()
        return {
            "total_cases": total,
            "positive_case_count": positive,
            "negative_case_count": negative,
            "t0_only_count": t0_only,
            "already_ran_count": already_ran,
            "weak_material_count": weak_mat,
            "by_judgement": by_judgement,
            "by_catalyst_category": by_catalyst,
            "by_setup_type": by_setup,
            "by_volume_type": by_volume,
            "by_chart_type": by_chart,
        }
    finally:
        db.close()


def get_feature_vectors_for_matching(limit: int = 1000) -> List[Dict]:
    """類似度マッチング用に feature_vectors をまとめて取得"""
    db: Session = SessionLocal()
    try:
        rows = db.query(AARFeatureVector).join(
            AARAnalysisCase, AARFeatureVector.case_id == AARAnalysisCase.id
        ).limit(limit).all()
        result = []
        for r in rows:
            c = db.query(AARAnalysisCase).filter(AARAnalysisCase.id == r.case_id).first()
            if not c:
                continue
            result.append({
                "case_id": r.case_id,
                "symbol": r.symbol,
                "move_date": r.move_date,
                "is_positive": c.is_positive_case,
                "is_negative": c.is_negative_case,
                "setup_type": c.setup_type,
                "volume_type": c.volume_type,
                "chart_type": c.chart_type,
                "catalyst_category": c.catalyst_category,
                "t1_judgement": c.t1_judgement,
                "t1_volume_ratio_20d": r.t1_volume_ratio_20d,
                "t1_price_change_5d": r.t1_price_change_5d,
                "t1_price_change_20d": r.t1_price_change_20d,
                "t1_ma25_deviation": r.t1_ma25_deviation,
                "t1_support_distance": r.t1_support_distance,
                "t1_resistance_upside": r.t1_resistance_upside,
                "t1_overextension_score": r.t1_overextension_score,
                "t1_range_break_flag": r.t1_range_break_flag,
                "t1_high_close_flag": r.t1_high_close_flag,
                "hit_20_percent": r.hit_20_percent,
            })
        return result
    finally:
        db.close()


def delete_analysis_case(case_id: int) -> bool:
    db: Session = SessionLocal()
    try:
        deleted = db.query(AARAnalysisCase).filter(AARAnalysisCase.id == case_id).delete()
        db.query(AARFeatureVector).filter(AARFeatureVector.case_id == case_id).delete()
        db.query(AAROHLCVSnapshot).filter(AAROHLCVSnapshot.case_id == case_id).delete()
        db.commit()
        return deleted > 0
    finally:
        db.close()
