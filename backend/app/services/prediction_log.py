"""予測ログ・自動検証・教師データ化サービス

予測スナップショットを固定保存し、後日の値動きで自動検証する。
失敗ケースは negative case として AAR 教師データに追加する。
"""
from typing import Dict, List, Optional
from datetime import datetime, date, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models.models import (
    PredictionLog, PredictionOutcome, PredictionReview,
    AARAnalysisCase, AARFeatureVector,
)
from app.services.price_fetcher import get_stock_data


# ========== 保存 ==========
def save_prediction_log(result: Dict, entry_plan: Dict) -> int:
    """ランキング結果と entry_plan からスナップショット保存"""
    db: Session = SessionLocal()
    try:
        log = PredictionLog(
            symbol=result.get("symbol"),
            yahoo_symbol=result.get("symbol"),
            name=result.get("name"),
            market=result.get("market"),
            prediction_date=result.get("date") or date.today().isoformat(),
            current_price_at_prediction=result.get("price"),
            jpy_price_at_prediction=result.get("jpy_price"),
            prediction_label=result.get("prediction_label"),
            final_prediction_score=result.get("final_prediction_score"),
            entry_timing_type=result.get("entry_timing_type"),
            entry_type=entry_plan.get("entry_type"),
            entry_zone_a_low=entry_plan.get("entry_zone_a_low"),
            entry_zone_a_high=entry_plan.get("entry_zone_a_high"),
            entry_zone_b_low=entry_plan.get("entry_zone_b_low"),
            entry_zone_b_high=entry_plan.get("entry_zone_b_high"),
            breakout_trigger_price=entry_plan.get("breakout_trigger_price"),
            stop_loss_price=entry_plan.get("stop_loss_price"),
            take_profit_1=entry_plan.get("take_profit_1"),
            take_profit_2=entry_plan.get("take_profit_2"),
            max_chase_price=entry_plan.get("max_chase_price"),
            chase_prohibited=entry_plan.get("chase_prohibited"),
            catalyst_quality_score=result.get("catalyst_quality_score"),
            catalyst_continuity_score=result.get("catalyst_continuity_score"),
            pre_night_signal_score=result.get("pre_night_signal_score"),
            pattern_similarity_score=result.get("pattern_similarity_score"),
            positive_case_similarity=result.get("positive_case_similarity"),
            negative_case_similarity=result.get("negative_case_similarity"),
            overextension_risk_score=result.get("overextension_risk_score"),
            bad_news_vacuum_score=result.get("bad_news_vacuum_score"),
            material_confirmed=result.get("material_confirmed", False),
            catalyst_category=result.get("catalyst_category") or "材料不明",
            matched_past_cases=result.get("matched_past_cases") or [],
            reason_summary=result.get("reason_summary"),
            avoid_condition=result.get("avoid_condition"),
            data_freshness_status=result.get("freshness_status"),
            chart_state=result.get("chart_cycle_state"),
            volume_cycle_state=result.get("volume_cycle_state"),
            support_line=result.get("support_line"),
            resistance_line=result.get("resistance_line"),
            ma25_deviation=result.get("ma25_deviation"),
            status="open",
        )
        db.add(log)
        db.commit()
        return log.id
    finally:
        db.close()


def list_prediction_logs(limit: int = 200, status: Optional[str] = None) -> Dict:
    db: Session = SessionLocal()
    try:
        q = db.query(PredictionLog)
        if status:
            q = q.filter(PredictionLog.status == status)
        total = q.count()
        rows = q.order_by(PredictionLog.id.desc()).limit(limit).all()
        return {
            "total": total,
            "items": [_log_to_dict(r) for r in rows],
        }
    finally:
        db.close()


def get_prediction_log(log_id: int) -> Optional[Dict]:
    db: Session = SessionLocal()
    try:
        r = db.query(PredictionLog).filter(PredictionLog.id == log_id).first()
        if not r:
            return None
        review = db.query(PredictionReview).filter(PredictionReview.prediction_log_id == log_id).first()
        out = (db.query(PredictionOutcome)
               .filter(PredictionOutcome.prediction_log_id == log_id)
               .order_by(PredictionOutcome.trading_days_elapsed.desc()).all())
        d = _log_to_dict(r)
        d["review"] = _review_to_dict(review) if review else None
        d["outcomes"] = [_outcome_to_dict(o) for o in out]
        return d
    finally:
        db.close()


def delete_prediction_log(log_id: int) -> bool:
    db: Session = SessionLocal()
    try:
        db.query(PredictionOutcome).filter(PredictionOutcome.prediction_log_id == log_id).delete()
        db.query(PredictionReview).filter(PredictionReview.prediction_log_id == log_id).delete()
        n = db.query(PredictionLog).filter(PredictionLog.id == log_id).delete()
        db.commit()
        return n > 0
    finally:
        db.close()


# ========== 結果更新 ==========
def update_outcomes(log_id: int) -> Dict:
    """予測ログ1件について、最新の価格データから outcomes を更新"""
    db: Session = SessionLocal()
    try:
        log = db.query(PredictionLog).filter(PredictionLog.id == log_id).first()
        if not log:
            return {"status": "failed", "error": "not found"}

        df = get_stock_data(log.yahoo_symbol or log.symbol, period="3mo", market=log.market)
        if df is None or df.empty:
            return {"status": "failed", "error": "price data unavailable"}

        df = df.sort_values("date").reset_index(drop=True)
        # 予測日以降の行
        pred_date = log.prediction_date
        future = df[df["date"].astype(str) > pred_date]
        if len(future) == 0:
            return {"status": "no_data_yet", "message": f"予測日 {pred_date} 以降のデータがまだありません"}

        # 既存outcomesを削除し再生成
        db.query(PredictionOutcome).filter(PredictionOutcome.prediction_log_id == log_id).delete()

        entry_price = log.current_price_at_prediction or 0
        if entry_price <= 0:
            return {"status": "failed", "error": "no entry_price"}

        outcomes_created = []
        running_max_gain = 0.0
        running_max_dd = 0.0
        hit_20 = False
        sl_hit = False
        tp1_hit = False
        tp2_hit = False
        trigger_hit = False

        targets = [1, 3, 5, 10, 20]
        for elapsed, row in enumerate(future.itertuples(index=False), 1):
            close = float(row.close)
            high = float(row.high)
            low = float(row.low)
            ret_close = (close - entry_price) / entry_price * 100
            ret_high = (high - entry_price) / entry_price * 100
            ret_low = (low - entry_price) / entry_price * 100
            running_max_gain = max(running_max_gain, ret_high)
            running_max_dd = min(running_max_dd, ret_low)
            if ret_high >= 20:
                hit_20 = True
            if log.take_profit_1 and high >= log.take_profit_1:
                tp1_hit = True
            if log.take_profit_2 and high >= log.take_profit_2:
                tp2_hit = True
            if log.stop_loss_price and low <= log.stop_loss_price:
                sl_hit = True
            if log.breakout_trigger_price and high >= log.breakout_trigger_price:
                trigger_hit = True

            if elapsed in targets:
                o = PredictionOutcome(
                    prediction_log_id=log_id,
                    symbol=log.symbol,
                    prediction_date=log.prediction_date,
                    check_date=str(row.date),
                    trading_days_elapsed=elapsed,
                    close_price=close,
                    high_price=high,
                    low_price=low,
                    volume=float(row.volume) if hasattr(row, "volume") else None,
                    return_from_prediction=ret_close,
                    max_gain_so_far=running_max_gain,
                    max_drawdown_so_far=running_max_dd,
                    hit_20_percent=hit_20,
                    hit_take_profit_1=tp1_hit,
                    hit_take_profit_2=tp2_hit,
                    stop_loss_hit=sl_hit,
                    trigger_hit=trigger_hit,
                )
                db.add(o)
                outcomes_created.append(elapsed)

            if elapsed >= 20:
                break

        db.commit()
        return {
            "status": "ok",
            "log_id": log_id,
            "outcomes_created": outcomes_created,
            "max_gain": round(running_max_gain, 2),
            "max_drawdown": round(running_max_dd, 2),
            "hit_20_percent": hit_20,
            "stop_loss_hit": sl_hit,
            "trigger_hit": trigger_hit,
        }
    finally:
        db.close()


def update_all_outcomes(limit: int = 100) -> Dict:
    """open状態の全予測ログのoutcomesを更新"""
    db: Session = SessionLocal()
    try:
        logs = db.query(PredictionLog).filter(PredictionLog.status == "open").limit(limit).all()
        log_ids = [l.id for l in logs]
    finally:
        db.close()

    updated = 0
    failed = 0
    for lid in log_ids:
        res = update_outcomes(lid)
        if res.get("status") == "ok":
            updated += 1
        else:
            failed += 1
    return {"updated": updated, "failed": failed, "total_checked": len(log_ids)}


# ========== 検証 ==========
def review_prediction(log_id: int) -> Dict:
    """予測ログを検証し、success_label と failure_reason を判定"""
    db: Session = SessionLocal()
    try:
        log = db.query(PredictionLog).filter(PredictionLog.id == log_id).first()
        if not log:
            return {"status": "failed", "error": "not found"}

        outcomes = (db.query(PredictionOutcome)
                    .filter(PredictionOutcome.prediction_log_id == log_id)
                    .order_by(PredictionOutcome.trading_days_elapsed.desc()).all())
        if not outcomes:
            return {"status": "no_outcomes", "message": "update_outcomes を先に実行してください"}

        latest = outcomes[0]
        max_gain = latest.max_gain_so_far or 0
        max_dd = latest.max_drawdown_so_far or 0
        hit_20 = latest.hit_20_percent
        sl_hit = latest.stop_loss_hit
        trigger_hit = latest.trigger_hit
        tp1_hit = latest.hit_take_profit_1
        elapsed = latest.trading_days_elapsed or 0

        pred_label = log.prediction_label or ""

        # success_label 判定
        success_label = "未判定"
        success_score = 0.0
        failed_cat = None
        failed_detail = None
        entry_worked = False

        is_avoid_label = any(k in pred_label for k in ["上がり切り警戒", "T0後追い警戒", "除外"])

        if is_avoid_label:
            # 見送り判定が正解かどうか
            if max_gain < 10:
                success_label = "見送り正解"
                success_score = 70.0
            elif sl_hit or max_dd <= -10:
                success_label = "見送り正解"
                success_score = 85.0
            elif max_gain >= 20 and not sl_hit:
                # 見送ったが上がった → 機会損失
                success_label = "失敗"
                success_score = 30.0
                failed_cat = "類似パターン誤判定"
                failed_detail = f"見送り判定したが {max_gain:.1f}% 上昇した(機会損失)"
            else:
                success_label = "見送り正解"
                success_score = 50.0
        else:
            # 候補系
            if hit_20 and not sl_hit:
                success_label = "成功"
                success_score = 95.0
                entry_worked = True
            elif tp1_hit and not sl_hit:
                success_label = "成功"
                success_score = 80.0
                entry_worked = True
            elif max_gain >= 10 and not sl_hit:
                success_label = "条件付き成功"
                success_score = 60.0
                entry_worked = True
            elif sl_hit:
                success_label = "失敗"
                success_score = 10.0
                failed_cat = _diagnose_failure(log, latest)
                failed_detail = f"損切りライン {log.stop_loss_price} に到達"
            elif max_gain < 10 and elapsed >= 5:
                success_label = "失敗"
                success_score = 25.0
                failed_cat = _diagnose_failure(log, latest)
                failed_detail = f"{elapsed}営業日で最大{max_gain:.1f}%しか上昇せず"
            elif elapsed < 5:
                success_label = "未判定"
                success_score = 0
            else:
                success_label = "条件付き成功" if max_gain >= 5 else "失敗"
                if success_label == "失敗":
                    failed_cat = _diagnose_failure(log, latest)
                    failed_detail = f"max_gain={max_gain:.1f}% / max_dd={max_dd:.1f}%"

        ai_comment = _generate_review_comment(log, latest, success_label, failed_cat)

        # 教師データ化フラグ
        save_positive = success_label in ("成功",) and not is_avoid_label
        save_negative = success_label in ("失敗",) or (is_avoid_label and success_label in ("見送り正解",))

        # 既存レビュー削除 & 新規作成
        db.query(PredictionReview).filter(PredictionReview.prediction_log_id == log_id).delete()
        rev = PredictionReview(
            prediction_log_id=log_id,
            symbol=log.symbol,
            prediction_date=log.prediction_date,
            review_date=date.today().isoformat(),
            success_label=success_label,
            success_score=success_score,
            max_gain=max_gain,
            max_drawdown=max_dd,
            hit_20_percent=hit_20,
            stop_loss_hit=sl_hit,
            trigger_hit=trigger_hit,
            entry_plan_worked=entry_worked,
            failed_reason_category=failed_cat,
            failed_reason_detail=failed_detail,
            ai_review_comment=ai_comment,
            should_save_as_positive_training=save_positive,
            should_save_as_negative_training=save_negative,
            saved_as_training=False,
        )
        db.add(rev)
        log.status = "reviewed"
        db.commit()

        return {
            "status": "ok",
            "log_id": log_id,
            "review": _review_to_dict(rev),
        }
    finally:
        db.close()


def review_all() -> Dict:
    """outcomesが揃っている全予測ログをレビュー"""
    db: Session = SessionLocal()
    try:
        log_ids = [l.id for l in db.query(PredictionLog).all()]
    finally:
        db.close()

    n_ok = 0; n_failed = 0
    for lid in log_ids:
        r = review_prediction(lid)
        if r.get("status") == "ok":
            n_ok += 1
        else:
            n_failed += 1
    return {"reviewed": n_ok, "skipped": n_failed, "total": len(log_ids)}


def _diagnose_failure(log: PredictionLog, outcome: PredictionOutcome) -> str:
    """失敗理由カテゴリを推定"""
    overext = log.overextension_risk_score or 0
    if overext >= 60:
        return "すでに上がり切っていた"
    if log.ma25_deviation and log.ma25_deviation >= 40:
        return "25MA乖離が大きすぎた"
    if not log.material_confirmed:
        return "材料が弱かった"
    if (log.negative_case_similarity or 0) > (log.positive_case_similarity or 0):
        return "類似パターン誤判定"
    if outcome.stop_loss_hit:
        return "損切りラインが遠すぎた"
    if outcome.max_gain_so_far is not None and outcome.max_gain_so_far < 5:
        return "出来高が続かなかった"
    return "その他"


def _generate_review_comment(log: PredictionLog, outcome: PredictionOutcome, label: str, failed_cat: Optional[str]) -> str:
    """AAR形式の振り返りコメント生成"""
    title = "予測成功AAR" if label == "成功" else ("予測失敗AAR" if label == "失敗" else "予測検証メモ")
    lines = [
        f"【{title}】",
        f"銘柄: {log.name} ({log.symbol})",
        f"予測日: {log.prediction_date}",
        f"予測ラベル: {log.prediction_label}",
        f"予測スコア: {log.final_prediction_score}",
        f"結果: {label}",
        f"最大上昇率: {outcome.max_gain_so_far:.2f}%",
        f"最大下落率: {outcome.max_drawdown_so_far:.2f}%",
        "",
    ]
    if label == "成功":
        lines += [
            "【効いた条件】",
            f"・catalyst_category: {log.catalyst_category}",
            f"・volume_cycle: {log.volume_cycle_state}",
            f"・chart_state: {log.chart_state}",
            f"・上値余地: 抵抗線={log.resistance_line}",
            "",
            "【教師データ化】 positive",
            "",
            "【一文まとめ】",
            f"{log.prediction_label}の判定が機能し、{outcome.max_gain_so_far:.1f}%まで上昇。",
        ]
    elif label == "失敗":
        lines += [
            "【当初の予測根拠】",
            f"・{log.reason_summary or '-'}",
            "",
            "【実際に起きたこと】",
            f"・max_gain={outcome.max_gain_so_far:.2f}% / max_drawdown={outcome.max_drawdown_so_far:.2f}%",
            f"・stop_loss_hit={outcome.stop_loss_hit} / trigger_hit={outcome.trigger_hit}",
            "",
            "【外れた理由】",
            f"・カテゴリ: {failed_cat}",
            f"・avoid_condition: {log.avoid_condition or '-'}",
            "",
            "【次回から減点すべき条件】",
            f"・{failed_cat} 類似時は信頼度を下げる",
            "",
            "【教師データ化】 negative",
            "",
            "【一文まとめ】",
            f"{log.prediction_label}と判定したが {failed_cat or 'その他'} により失敗。",
        ]
    else:
        lines += [
            f"【判定根拠】",
            f"・{log.reason_summary or '-'}",
            f"・avoid_condition: {log.avoid_condition or '-'}",
            "",
            "【教師データ化】 watch",
            "",
            f"【一文まとめ】{log.prediction_label} → {label}。",
        ]
    lines.append("")
    lines.append("※ これは投資助言ではありません。分析・学習目的の自動振り返りです。")
    return "\n".join(lines)


# ========== AAR教師データへの追加 ==========
def save_review_as_training(log_id: int) -> Dict:
    """レビュー結果を AAR教師データ (AARAnalysisCase + AARFeatureVector) に保存"""
    db: Session = SessionLocal()
    try:
        log = db.query(PredictionLog).filter(PredictionLog.id == log_id).first()
        rev = db.query(PredictionReview).filter(PredictionReview.prediction_log_id == log_id).first()
        if not log or not rev:
            return {"status": "failed", "error": "log or review not found"}
        if rev.saved_as_training and rev.saved_aar_case_id:
            return {"status": "already_saved", "case_id": rev.saved_aar_case_id}

        is_pos = bool(rev.should_save_as_positive_training)
        is_neg = bool(rev.should_save_as_negative_training)

        case = AARAnalysisCase(
            input_case_id=None,
            symbol=log.symbol,
            yahoo_symbol=log.yahoo_symbol,
            name=log.name,
            market=log.market,
            move_date=log.prediction_date,
            move_percent=rev.max_gain,
            catalyst=log.catalyst_category,
            catalyst_category=log.catalyst_category,
            catalyst_timing="prediction_review",
            catalyst_strength_score=log.catalyst_quality_score,
            catalyst_continuity_score=log.catalyst_continuity_score,
            material_confirmed=log.material_confirmed,
            material_source_rank="prediction_review",
            t1_judgement=("入る余地あり" if is_pos else "見送り"),
            t1_entry_possible=("あり" if is_pos else "なし"),
            t1_entry_type=log.entry_type,
            setup_type=log.prediction_label,
            volume_type=log.volume_cycle_state,
            chart_type=log.chart_state,
            overextension_risk_score=log.overextension_risk_score,
            weak_material_flag=(not log.material_confirmed),
            t0_only_flag=("T0後追い" in (log.prediction_label or "")),
            already_ran_flag=((log.overextension_risk_score or 0) >= 70),
            tags=[rev.failed_reason_category] if rev.failed_reason_category else [],
            failure_warnings=rev.failed_reason_detail,
            is_positive_case=is_pos,
            is_negative_case=is_neg,
            nlm_data_raw=None,
        )
        db.add(case)
        db.flush()

        fv = AARFeatureVector(
            case_id=case.id,
            symbol=log.symbol,
            move_date=log.prediction_date,
            feature_asof_date=log.prediction_date,
            t1_close=log.current_price_at_prediction,
            t1_ma25_deviation=log.ma25_deviation,
            t1_overextension_score=log.overextension_risk_score,
            t1_fresh_material_flag=log.material_confirmed,
            t1_unknown_material_flag=(log.catalyst_category == "材料不明"),
            t0_result_move_percent=None,
            t1_to_t5_max_gain=None,
            t1_to_t20_max_gain=rev.max_gain,
            t1_to_t20_max_drawdown=rev.max_drawdown,
            hit_20_percent=rev.hit_20_percent,
        )
        db.add(fv)
        rev.saved_as_training = True
        rev.saved_aar_case_id = case.id
        db.commit()
        return {"status": "ok", "case_id": case.id, "is_positive": is_pos, "is_negative": is_neg}
    finally:
        db.close()


def save_all_reviewed_as_training() -> Dict:
    db: Session = SessionLocal()
    try:
        reviews = (db.query(PredictionReview)
                   .filter(PredictionReview.saved_as_training == False)
                   .filter((PredictionReview.should_save_as_positive_training == True) |
                           (PredictionReview.should_save_as_negative_training == True))
                   .all())
        log_ids = [r.prediction_log_id for r in reviews]
    finally:
        db.close()

    saved = 0; failed = 0
    for lid in log_ids:
        r = save_review_as_training(lid)
        if r.get("status") == "ok":
            saved += 1
        else:
            failed += 1
    return {"saved": saved, "failed": failed, "total_candidates": len(log_ids)}


# ========== サマリ ==========
def review_summary() -> Dict:
    db: Session = SessionLocal()
    try:
        total_logs = db.query(PredictionLog).count()
        reviewed = db.query(PredictionReview).count()
        open_count = db.query(PredictionLog).filter(PredictionLog.status == "open").count()

        by_label = dict(db.query(PredictionReview.success_label, func.count(PredictionReview.id))
                        .group_by(PredictionReview.success_label).all())
        by_failed = dict(db.query(PredictionReview.failed_reason_category, func.count(PredictionReview.id))
                         .filter(PredictionReview.failed_reason_category.isnot(None))
                         .group_by(PredictionReview.failed_reason_category).all())

        hit_20 = db.query(PredictionReview).filter(PredictionReview.hit_20_percent == True).count()
        sl_hit = db.query(PredictionReview).filter(PredictionReview.stop_loss_hit == True).count()
        saved_training = db.query(PredictionReview).filter(PredictionReview.saved_as_training == True).count()

        avg_gain = db.query(func.avg(PredictionReview.max_gain)).scalar() or 0
        avg_dd = db.query(func.avg(PredictionReview.max_drawdown)).scalar() or 0

        # ラベル別成績
        from collections import defaultdict
        by_pred_label_stats: Dict = defaultdict(lambda: {"count": 0, "success": 0, "failed": 0, "avg_gain": []})
        joined = db.query(PredictionLog.prediction_label, PredictionReview.success_label, PredictionReview.max_gain).join(
            PredictionReview, PredictionLog.id == PredictionReview.prediction_log_id
        ).all()
        for pred_label, success, gain in joined:
            entry = by_pred_label_stats[pred_label or "未分類"]
            entry["count"] += 1
            if success == "成功":
                entry["success"] += 1
            elif success == "失敗":
                entry["failed"] += 1
            if gain is not None:
                entry["avg_gain"].append(float(gain))
        by_pred_label_summary = {
            k: {
                "count": v["count"],
                "success": v["success"],
                "failed": v["failed"],
                "win_rate": round(v["success"] / max(1, v["count"]) * 100, 1),
                "avg_gain": round(sum(v["avg_gain"]) / max(1, len(v["avg_gain"])), 2),
            }
            for k, v in by_pred_label_stats.items()
        }

        return {
            "total_logs": total_logs,
            "reviewed_count": reviewed,
            "open_count": open_count,
            "by_success_label": by_label,
            "by_failed_reason": by_failed,
            "hit_20_count": hit_20,
            "stop_loss_hit_count": sl_hit,
            "saved_as_training_count": saved_training,
            "avg_max_gain": round(float(avg_gain), 2),
            "avg_max_drawdown": round(float(avg_dd), 2),
            "by_prediction_label": by_pred_label_summary,
        }
    finally:
        db.close()


# ========== シリアライザ ==========
def _log_to_dict(r: PredictionLog) -> Dict:
    return {
        "id": r.id,
        "symbol": r.symbol,
        "name": r.name,
        "market": r.market,
        "prediction_date": r.prediction_date,
        "prediction_datetime": r.prediction_datetime.isoformat() if r.prediction_datetime else None,
        "current_price_at_prediction": r.current_price_at_prediction,
        "jpy_price_at_prediction": r.jpy_price_at_prediction,
        "prediction_label": r.prediction_label,
        "final_prediction_score": r.final_prediction_score,
        "entry_timing_type": r.entry_timing_type,
        "entry_type": r.entry_type,
        "entry_zone_a_low": r.entry_zone_a_low,
        "entry_zone_a_high": r.entry_zone_a_high,
        "breakout_trigger_price": r.breakout_trigger_price,
        "stop_loss_price": r.stop_loss_price,
        "take_profit_1": r.take_profit_1,
        "take_profit_2": r.take_profit_2,
        "max_chase_price": r.max_chase_price,
        "chase_prohibited": r.chase_prohibited,
        "catalyst_quality_score": r.catalyst_quality_score,
        "catalyst_continuity_score": r.catalyst_continuity_score,
        "pre_night_signal_score": r.pre_night_signal_score,
        "pattern_similarity_score": r.pattern_similarity_score,
        "positive_case_similarity": r.positive_case_similarity,
        "negative_case_similarity": r.negative_case_similarity,
        "overextension_risk_score": r.overextension_risk_score,
        "material_confirmed": r.material_confirmed,
        "catalyst_category": r.catalyst_category,
        "matched_past_cases": r.matched_past_cases,
        "reason_summary": r.reason_summary,
        "avoid_condition": r.avoid_condition,
        "data_freshness_status": r.data_freshness_status,
        "chart_state": r.chart_state,
        "volume_cycle_state": r.volume_cycle_state,
        "support_line": r.support_line,
        "resistance_line": r.resistance_line,
        "ma25_deviation": r.ma25_deviation,
        "status": r.status,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _outcome_to_dict(o: PredictionOutcome) -> Dict:
    return {
        "trading_days_elapsed": o.trading_days_elapsed,
        "check_date": o.check_date,
        "close_price": o.close_price,
        "return_from_prediction": o.return_from_prediction,
        "max_gain_so_far": o.max_gain_so_far,
        "max_drawdown_so_far": o.max_drawdown_so_far,
        "hit_20_percent": o.hit_20_percent,
        "stop_loss_hit": o.stop_loss_hit,
        "trigger_hit": o.trigger_hit,
    }


def _review_to_dict(r: Optional[PredictionReview]) -> Optional[Dict]:
    if r is None:
        return None
    return {
        "id": r.id,
        "success_label": r.success_label,
        "success_score": r.success_score,
        "max_gain": r.max_gain,
        "max_drawdown": r.max_drawdown,
        "hit_20_percent": r.hit_20_percent,
        "stop_loss_hit": r.stop_loss_hit,
        "trigger_hit": r.trigger_hit,
        "entry_plan_worked": r.entry_plan_worked,
        "failed_reason_category": r.failed_reason_category,
        "failed_reason_detail": r.failed_reason_detail,
        "ai_review_comment": r.ai_review_comment,
        "should_save_as_positive_training": r.should_save_as_positive_training,
        "should_save_as_negative_training": r.should_save_as_negative_training,
        "saved_as_training": r.saved_as_training,
        "saved_aar_case_id": r.saved_aar_case_id,
        "review_date": r.review_date,
    }


def list_reviews(limit: int = 200) -> Dict:
    db: Session = SessionLocal()
    try:
        joined = (db.query(PredictionLog, PredictionReview)
                  .outerjoin(PredictionReview, PredictionLog.id == PredictionReview.prediction_log_id)
                  .order_by(PredictionLog.id.desc()).limit(limit).all())
        items = []
        for log, rev in joined:
            d = _log_to_dict(log)
            d["review"] = _review_to_dict(rev) if rev else None
            items.append(d)
        return {"total": len(items), "items": items}
    finally:
        db.close()
