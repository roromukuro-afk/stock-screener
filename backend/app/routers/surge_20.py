"""20%急騰到達候補 API"""
import threading
from typing import List, Optional, Dict
from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import surge_20
from app.services.surge_20 import (
    detect_one_day_surges, detect_multi_day_hit_20,
    _save_surge_events, extract_pre_features_for_recent_events,
    generate_negative_cases_for_symbol,
)
from app.utils import clean_for_json


router = APIRouter(prefix="/api/surge-20", tags=["surge-20"])


_progress: Dict = {"running": False, "step": "", "message": ""}


def _set_progress(**kw):
    _progress.update(kw)


# ============== ランキング ==============
class GenerateRankingsRequest(BaseModel):
    market: str = "JP"
    snapshot_date: Optional[str] = None
    top_n: int = 100
    ranking_types: Optional[List[str]] = None  # None=全種類
    max_universe: int = 300  # Render Free対策
    async_mode: bool = True  # 大量銘柄では必ずTrue推奨


def _run_rankings_sync(req_dict: Dict):
    """background thread で実行"""
    market = req_dict.get("market", "JP")
    rts = req_dict.get("ranking_types")
    if rts:
        for rt in rts:
            try:
                surge_20.generate_ranking_from_ohlcv(
                    rt, market=market,
                    snapshot_date=req_dict.get("snapshot_date"),
                    top_n=req_dict.get("top_n", 100),
                    max_universe=req_dict.get("max_universe", 300),
                )
            except Exception as e:
                print(f"ranking gen {rt} failed: {e}")
    else:
        surge_20.generate_all_rankings(
            market=market,
            snapshot_date=req_dict.get("snapshot_date"),
            top_n=req_dict.get("top_n", 100),
            max_universe=req_dict.get("max_universe", 300),
        )


@router.post("/generate-rankings-from-ohlcv")
def generate_rankings_from_ohlcv(req: GenerateRankingsRequest):
    """ランキング生成。async_mode=True なら background thread で実行 (推奨)"""
    if req.async_mode:
        t = threading.Thread(target=_run_rankings_sync, args=(req.model_dump(),), daemon=True)
        t.start()
        return {"status": "started", "message": f"ランキング生成を background で開始 (market={req.market})",
                "note": "/api/surge-20/recent-snapshots で確認してください"}
    # 同期 (小規模テスト用)
    if req.ranking_types:
        out = {}
        for rt in req.ranking_types:
            out[rt] = surge_20.generate_ranking_from_ohlcv(
                rt, market=req.market, snapshot_date=req.snapshot_date,
                top_n=req.top_n, max_universe=req.max_universe,
            )
        return clean_for_json({"status": "ok", "rankings": out})
    r = surge_20.generate_all_rankings(market=req.market, snapshot_date=req.snapshot_date,
                                       top_n=req.top_n, max_universe=req.max_universe)
    return clean_for_json(r)


@router.get("/recent-snapshots")
def recent_snapshots(limit: int = 20):
    return clean_for_json({"items": surge_20.list_recent_snapshots(limit=limit)})


@router.get("/snapshot/{snapshot_id}/items")
def snapshot_items(snapshot_id: int, limit: int = 100):
    return clean_for_json({"snapshot_id": snapshot_id,
                           "items": surge_20.list_snapshot_items(snapshot_id, limit=limit)})


# ============== 手動取込 ==============
class ImportRankingRequest(BaseModel):
    ranking_type: str  # custom_uploaded_ranking 等
    market: str = "JP"
    snapshot_date: Optional[str] = None
    source_name: Optional[str] = "user_import"
    items: List[Dict]  # symbol, name, rank, gain_percent (imported), current_price?


@router.post("/import-ranking")
def import_ranking(req: ImportRankingRequest):
    """手動取込: items を保存し、OHLCVで再検証して gain_percent_diff を計算"""
    from app.database import SessionLocal
    from app.models.models import SurgeRankingSnapshot, SurgeRankingItem

    snap_date = req.snapshot_date or date.today().isoformat()
    db = SessionLocal()
    try:
        snap = SurgeRankingSnapshot(
            ranking_type=req.ranking_type,
            market=req.market,
            snapshot_date=snap_date,
            source_name=req.source_name,
            auto_generated=False,
            imported_by_user=True,
            total_items=len(req.items),
            calculation_method="imported_then_verified",
        )
        db.add(snap); db.flush()
        snap_id = snap.id

        # window 自動推定
        from app.services.surge_20 import RANKING_WINDOWS, _list_history
        window = RANKING_WINDOWS.get(req.ranking_type, 5)

        for idx, it in enumerate(req.items, 1):
            sym = it.get("symbol", "").strip()
            if not sym:
                continue
            imported_gain = it.get("gain_percent")
            calc_gain = None
            warn = None
            df = _list_history(sym)
            if df is not None and len(df) >= window + 1:
                df = df.sort_values("date").reset_index(drop=True)
                df_until = df[df["date"].astype(str) <= snap_date]
                if len(df_until) >= window + 1:
                    try:
                        cp = float(df_until.iloc[-1]["close"])
                        sp = float(df_until.iloc[-1 - window]["close"])
                        if sp > 0:
                            calc_gain = round((cp - sp) / sp * 100, 3)
                    except Exception:
                        pass
            diff = None
            if imported_gain is not None and calc_gain is not None:
                diff = round(float(imported_gain) - calc_gain, 3)
                if abs(diff) > 5.0:
                    warn = f"imported {imported_gain}% vs OHLCV {calc_gain}% (diff {diff}%)"

            row = SurgeRankingItem(
                snapshot_id=snap_id,
                symbol=sym, name=it.get("name"), market=it.get("market") or req.market,
                rank=it.get("rank") or idx,
                current_price=it.get("current_price"),
                start_price=it.get("start_price"),
                imported_gain_percent=imported_gain,
                calculated_gain_percent=calc_gain,
                gain_percent_diff=diff,
                verified_by_ohlcv=calc_gain is not None,
                verification_warning=warn,
            )
            db.add(row)
        db.commit()
        return {"status": "ok", "snapshot_id": snap_id, "items": len(req.items)}
    finally:
        db.close()


# ============== イベント検出 ==============
class DetectRequest(BaseModel):
    market: str = "JP"
    max_symbols: int = 50
    async_mode: bool = True


@router.post("/detect-events")
def detect_events(req: DetectRequest):
    if req.async_mode:
        t = threading.Thread(
            target=surge_20.detect_events_for_universe,
            args=(req.market, req.max_symbols),
            daemon=True,
        )
        t.start()
        return {"status": "started", "message": f"イベント検出を background で開始 (market={req.market}, max={req.max_symbols})"}
    return clean_for_json(surge_20.detect_events_for_universe(market=req.market, max_symbols=req.max_symbols))


@router.post("/detect-one-day-surges")
def detect_one_day_surges(req: DetectRequest):
    """1日急騰のみ検出 (universe走査)"""
    from app.services import universe_db
    syms = universe_db.list_eligible_yahoo_symbols(
        markets=[req.market], max_count=req.max_symbols, include_adr=True
    )
    events = []
    for s in syms:
        try:
            events.extend(surge_20.detect_one_day_surges(s["yahoo_symbol"], s.get("market") or req.market))
        except Exception:
            pass
    saved = surge_20._save_surge_events(events, source_type="detected_from_ohlcv")
    return clean_for_json({"status": "ok", "events_detected": len(events), "events_saved_new": saved})


@router.get("/events")
def events(limit: int = 50, event_type: Optional[str] = None):
    return clean_for_json({"items": surge_20.list_recent_events(limit=limit, event_type=event_type)})


# ============== 特徴量 ==============
@router.post("/extract-pre-features")
def extract_pre_features(req: DetectRequest):
    if req.async_mode:
        t = threading.Thread(
            target=surge_20.extract_pre_features_for_recent_events,
            args=(req.max_symbols,),
            daemon=True,
        )
        t.start()
        return {"status": "started", "message": f"pre_features抽出を background で開始 (events={req.max_symbols})"}
    return surge_20.extract_pre_features_for_recent_events(limit=req.max_symbols)


# ============== 候補 ==============
@router.post("/build-candidates")
def build_candidates(req: DetectRequest):
    if req.async_mode:
        t = threading.Thread(
            target=surge_20.build_candidates,
            args=(req.market, req.max_symbols),
            daemon=True,
        )
        t.start()
        return {"status": "started", "message": f"候補生成を background で開始 (market={req.market}, max={req.max_symbols})"}
    return clean_for_json(surge_20.build_candidates(market=req.market, max_symbols=req.max_symbols))


@router.get("/candidates")
def get_candidates(market: str = "JP", max_symbols: int = 100):
    return clean_for_json(surge_20.build_candidates(market=market, max_symbols=max_symbols))


@router.get("/summary")
def summary():
    return clean_for_json(surge_20.get_summary())


# ============== Training data expansion ==============
class ExpandTrainingRequest(BaseModel):
    market: str = "JP"
    max_symbols: int = 300
    chunk_size: int = 30
    start_offset: int = 0
    priority_mode: str = "known_surge_first"
    # known_surge_first / smallcap_first / growth_market_first /
    # low_price_first / high_volume_first / all_eligible
    generate_negative_cases: bool = True
    extract_features_limit: int = 200
    async_mode: bool = True


def _select_priority_universe(priority_mode: str, market: str, max_symbols: int, start_offset: int) -> List[Dict]:
    """priority_mode に応じて universe を選定"""
    from app.services import universe_db
    from app.services.training_builder import KNOWN_SURGE_SEED_JP, KNOWN_SURGE_SEED_US

    if priority_mode == "known_surge_first":
        if market == "JP":
            seed = [{"symbol": s, "yahoo_symbol": s, "name": s, "market": "JP"} for s in KNOWN_SURGE_SEED_JP]
        elif market == "US":
            seed = [{"symbol": s, "yahoo_symbol": s, "name": s, "market": "US"} for s in KNOWN_SURGE_SEED_US]
        else:
            seed = ([{"symbol": s, "yahoo_symbol": s, "name": s, "market": "JP"} for s in KNOWN_SURGE_SEED_JP] +
                    [{"symbol": s, "yahoo_symbol": s, "name": s, "market": "US"} for s in KNOWN_SURGE_SEED_US])
        # seedの後に通常universe
        rest = universe_db.list_eligible_yahoo_symbols(markets=[market] if market != "ALL" else ["JP", "US"],
                                                       max_count=0, include_adr=True)
        seed_set = {x["symbol"] for x in seed}
        rest_filtered = [x for x in rest if x["symbol"] not in seed_set]
        combined = seed + rest_filtered
        return combined[start_offset: start_offset + max_symbols]

    if priority_mode == "smallcap_first":
        all_syms = universe_db.list_eligible_yahoo_symbols(
            markets=[market] if market != "ALL" else ["JP", "US"], max_count=0, include_adr=True
        )
        # 5桁以下の小型株を優先
        small = [s for s in all_syms if len(s.get("symbol", "").split(".")[0]) <= 5]
        return small[start_offset: start_offset + max_symbols]

    # default: all_eligible
    return universe_db.list_eligible_yahoo_symbols(
        markets=[market] if market != "ALL" else ["JP", "US"],
        max_count=max_symbols + start_offset, include_adr=True,
    )[start_offset: start_offset + max_symbols]


def _expand_training_sync(req_dict: Dict):
    """chunk処理で training データを拡張"""
    market = req_dict.get("market", "JP")
    max_symbols = req_dict.get("max_symbols", 300)
    chunk_size = req_dict.get("chunk_size", 30)
    start_offset = req_dict.get("start_offset", 0)
    priority_mode = req_dict.get("priority_mode", "known_surge_first")
    do_negative = req_dict.get("generate_negative_cases", True)
    extract_limit = req_dict.get("extract_features_limit", 200)

    syms = _select_priority_universe(priority_mode, market, max_symbols, start_offset)
    print(f"[expand-training] {priority_mode} → {len(syms)} symbols (offset={start_offset})")

    # chunk処理
    total_events = 0
    total_features = 0
    total_negatives = 0
    for chunk_start in range(0, len(syms), chunk_size):
        chunk = syms[chunk_start: chunk_start + chunk_size]
        chunk_events = []
        for s in chunk:
            sym = s["yahoo_symbol"]
            mk = s.get("market") or market
            try:
                chunk_events.extend(detect_one_day_surges(sym, mk))
                chunk_events.extend(detect_multi_day_hit_20(sym, mk))
            except Exception as e:
                print(f"detect failed {sym}: {e}")
        saved = _save_surge_events(chunk_events, source_type="detected_from_ohlcv")
        total_events += saved
        # 各chunk後 extract pre_features
        try:
            fres = extract_pre_features_for_recent_events(limit=extract_limit)
            total_features += fres.get("features_created", 0)
        except Exception as e:
            print(f"extract features chunk failed: {e}")
        # negative case生成
        if do_negative:
            for s in chunk:
                try:
                    n = generate_negative_cases_for_symbol(
                        s["yahoo_symbol"], s.get("market") or market, max_cases=15
                    )
                    total_negatives += n
                except Exception as e:
                    print(f"neg gen failed {s.get('symbol')}: {e}")
        print(f"[expand-training chunk {chunk_start//chunk_size+1}] events_saved={saved} features={total_features} negatives={total_negatives}")

    print(f"[expand-training DONE] events={total_events} features={total_features} negatives={total_negatives}")


@router.post("/expand-training")
def expand_training(req: ExpandTrainingRequest):
    """chunk処理で大規模拡張 (常にasync推奨)"""
    if req.async_mode:
        t = threading.Thread(target=_expand_training_sync, args=(req.model_dump(),), daemon=True)
        t.start()
        return {
            "status": "started",
            "message": f"教師データ拡張をbackgroundで開始 (market={req.market}, max={req.max_symbols}, chunk={req.chunk_size}, priority={req.priority_mode})",
            "note": "/api/surge-20/summary で進捗確認",
        }
    _expand_training_sync(req.model_dump())
    return clean_for_json(surge_20.get_summary())


# ============== negative生成単独 ==============
class NegativeGenRequest(BaseModel):
    market: str = "JP"
    max_symbols: int = 100
    max_per_symbol: int = 20
    async_mode: bool = True


@router.post("/generate-negative-cases")
def generate_negative_cases(req: NegativeGenRequest):
    if req.async_mode:
        t = threading.Thread(
            target=surge_20.generate_negative_cases_for_universe,
            args=(req.market, req.max_symbols, req.max_per_symbol),
            daemon=True,
        )
        t.start()
        return {"status": "started", "message": f"negative case生成をbackgroundで開始 (market={req.market}, max={req.max_symbols})"}
    return clean_for_json(surge_20.generate_negative_cases_for_universe(req.market, req.max_symbols, req.max_per_symbol))


@router.post("/consolidate-duplicates")
def consolidate_duplicates(min_gap_days: int = 5):
    return clean_for_json(surge_20.consolidate_duplicate_events(min_gap_days=min_gap_days))


# ============== data-quality ==============
@router.get("/data-quality")
def data_quality():
    return clean_for_json(surge_20.get_data_quality())


@router.post("/cleanup-orphan-features")
def cleanup_orphan_features():
    return surge_20.cleanup_orphan_pre_features()


# ============== prediction save/review ==============
class SaveCandidatePredictionRequest(BaseModel):
    symbol: str
    name: Optional[str] = None
    market: str = "JP"
    candidate_label: Optional[str] = None
    final_surge_20_score: Optional[float] = None
    prediction_horizon: str = "within_20d"
    target_return: float = 20.0
    current_price: Optional[float] = None
    entry_zone_low: Optional[float] = None
    entry_zone_high: Optional[float] = None
    stop_loss: Optional[float] = None
    first_target: Optional[float] = None
    second_target: Optional[float] = None
    reason_summary: Optional[str] = None
    risk_summary: Optional[str] = None
    positive_similarity: Optional[float] = None
    negative_similarity: Optional[float] = None
    similar_past_20_events: Optional[List[Dict]] = None


@router.post("/save-candidate-prediction")
def save_candidate_prediction(req: SaveCandidatePredictionRequest):
    return clean_for_json(surge_20.save_candidate_as_prediction(req.model_dump()))


@router.post("/review-predictions")
def review_predictions(limit: int = 200):
    if True:  # async by default
        t = threading.Thread(target=surge_20.review_surge_20_predictions, args=(limit,), daemon=True)
        t.start()
        return {"status": "started", "message": f"surge_20_prediction レビューをbackgroundで開始 (limit={limit})"}


@router.post("/save-reviewed-predictions-as-training")
def save_reviewed_as_training():
    return clean_for_json(surge_20.save_surge_20_reviews_as_training())


@router.get("/prediction-performance")
def prediction_performance():
    return clean_for_json(surge_20.get_surge_20_prediction_performance())


# ============== orchestrator + auto-save + candidates list ==============
class OrchestratorRequest(BaseModel):
    market: str = "JP"
    phase: str = "all"  # all / expand / candidates / review / data-quality


@router.post("/run-auto-orchestrator")
def run_auto_orchestrator(req: OrchestratorRequest):
    """surge-20 全フローを非同期実行 (CRON_SECRET不要なopen版)。busyなら409相当"""
    if surge_20.is_heavy_running():
        hs = surge_20.heavy_status()
        return {"status": "busy", "message": f"別の重い処理が実行中: {hs.get('task')}",
                "running_task": hs.get("task"), "started_at": hs.get("started_at")}
    t = threading.Thread(target=surge_20.run_auto_orchestrator,
                          args=(req.market, req.phase), daemon=True)
    t.start()
    return {"status": "started", "message": f"orchestrator開始 market={req.market} phase={req.phase}"}


@router.get("/heavy-status")
def heavy_status():
    """重い処理の実行中ステータス (軽量 polling用)"""
    return clean_for_json(surge_20.heavy_status())


@router.get("/light-status")
def light_status():
    """高負荷時でも返る軽量status (最小限のCOUNT)。例外でも500にしない。"""
    try:
        return clean_for_json(surge_20.get_light_status())
    except Exception as e:
        msg = str(e).strip().splitlines()
        return {"status": "degraded", "render_safe_to_run": False,
                "warnings": [(msg[0] if msg else type(e).__name__)[:300]],
                "hint": "POST /api/automation/ensure-schema を実行してください"}


class AutoSaveRequest(BaseModel):
    market: str = "JP"
    limit: int = 20
    min_score: float = 70.0


@router.post("/auto-save-top-candidates")
def auto_save_top_candidates(req: AutoSaveRequest):
    return clean_for_json(surge_20.auto_save_top_candidates(
        market=req.market, limit=req.limit, min_score=req.min_score,
    ))


class BuildSaveRequest(BaseModel):
    market: str = "JP"
    max_symbols: int = 200
    min_similarity: float = 0.4


def _build_and_save_locked(market, max_symbols, min_similarity):
    if not surge_20._acquire_heavy(f"build_candidates/{market}"):
        return
    try:
        surge_20.build_and_save_candidates(market=market, max_symbols=max_symbols, min_similarity=min_similarity)
    finally:
        surge_20._release_heavy()


@router.post("/build-and-save-candidates")
def build_and_save(req: BuildSaveRequest):
    """非同期 + lock。busyなら即status=busy"""
    if surge_20.is_heavy_running():
        hs = surge_20.heavy_status()
        return {"status": "busy", "running_task": hs.get("task")}
    t = threading.Thread(target=_build_and_save_locked,
                         args=(req.market, min(req.max_symbols, 80), req.min_similarity), daemon=True)
    t.start()
    return {"status": "started", "message": f"候補生成をbackgroundで開始 (market={req.market})"}


@router.get("/candidates-today")
def candidates_today(market: Optional[str] = None, limit: int = 100):
    from app.database import SessionLocal
    from app.models.models import Surge20Candidate
    today = date.today().isoformat()
    db = SessionLocal()
    try:
        q = (db.query(Surge20Candidate)
             .filter(Surge20Candidate.candidate_date == today))
        if market:
            q = q.filter(Surge20Candidate.market == market)
        rows = q.order_by(Surge20Candidate.final_surge_20_score.desc()).limit(limit).all()
        return clean_for_json({
            "candidate_date": today,
            "count": len(rows),
            "items": [{
                "id": r.id, "symbol": r.symbol, "name": r.name, "market": r.market,
                "candidate_label": r.candidate_label,
                "final_surge_20_score": r.final_surge_20_score,
                "current_price": r.current_price,
                "positive_similarity": r.positive_similarity,
                "negative_similarity": r.negative_similarity,
                "similarity_gap": r.similarity_gap,
                "overextension_score": r.overextension_score,
                "resistance_upside": r.resistance_upside,
                "support_distance": r.support_distance,
                "reason_summary": r.reason_summary,
                "risk_summary": r.risk_summary,
                "auto_saved_as_prediction": r.auto_saved_as_prediction,
                "prediction_log_id": r.prediction_log_id,
                # 新フィールド: マッチ理由 / 多horizon 確率 / 材料ブースト / 予測horizon
                "similar_past_20_events": r.similar_past_20_events,
                "horizon_distribution": getattr(r, "horizon_distribution", None),
                "catalyst_boost": getattr(r, "catalyst_boost", None),
                "prediction_horizon": r.prediction_horizon,
                "reason_summary": r.reason_summary,
            } for r in rows],
        })
    finally:
        db.close()


@router.get("/orchestrator-state")
def orchestrator_state():
    return clean_for_json(surge_20.get_orchestrator_state())


# ============== モデル版管理 (A/B & ロールバック) ==============
@router.post("/snapshot-model-version")
def snapshot_model_version(version_name: Optional[str] = None, activate: bool = True):
    """現在の動的重み・閾値・学習データ件数を model_versions に保存。
    A/B テスト・ロールバック用のスナップショット。"""
    from app.database import SessionLocal
    from app.models.models import (
        ModelVersion, TrainingFeatureVector, Surge20Event, Surge20PreFeature,
    )
    from app.services.predictor import compute_dynamic_weights, NUMERIC_WEIGHTS, NUMERIC_SCALES
    from datetime import datetime as _dt

    weights = compute_dynamic_weights()
    db = SessionLocal()
    try:
        pos_count = db.query(TrainingFeatureVector).filter(
            TrainingFeatureVector.case_type.in_(["positive_surge", "semi_positive_surge"])).count()
        neg_count = db.query(TrainingFeatureVector).filter(
            TrainingFeatureVector.case_type.in_([
                "negative_non_surge", "failed_overextended", "failed_weak_material",
                "failed_material_exhaustion", "failed_bad_news",
            ])).count()
        ev_count = db.query(Surge20Event).count()
        pf_count = db.query(Surge20PreFeature).count()
        vname = version_name or f"v_{_dt.utcnow().strftime('%Y%m%d_%H%M%S')}"
        # 同名チェック
        existing = db.query(ModelVersion).filter(ModelVersion.version_name == vname).first()
        if existing:
            return {"status": "exists", "version_name": vname, "id": existing.id}
        if activate:
            db.query(ModelVersion).update({ModelVersion.active: False})
        mv = ModelVersion(
            version_name=vname,
            training_case_count=pos_count + neg_count,
            positive_count=pos_count,
            negative_count=neg_count,
            review_count=0,
            weight_config={
                "dynamic_weights": weights,
                "base_weights": NUMERIC_WEIGHTS,
                "scales": NUMERIC_SCALES,
                "relative_day_weights": {"T-1": 3.0, "T-3": 2.0, "T-5": 1.5, "T-10": 1.0, "T-20": 0.5},
                "label_thresholds": {
                    "honmei_pos_min": 0.7, "honmei_diff_min": 0.1,
                    "within_20d_pos_min": 0.6, "within_20d_diff_min": 0.05,
                    "within_1m_pos_min": 0.5, "shutsdouhatsu_pos_min": 0.4,
                },
            },
            performance_summary={
                "events": ev_count, "pre_features": pf_count,
                "snapshot_at": _dt.utcnow().isoformat(),
            },
            active=activate,
        )
        db.add(mv); db.commit()
        return {"status": "ok", "id": mv.id, "version_name": vname,
                "training_case_count": pos_count + neg_count, "active": activate}
    finally:
        db.close()


@router.get("/model-versions")
def list_model_versions(limit: int = 20):
    """保存済モデル版一覧"""
    from app.database import SessionLocal
    from app.models.models import ModelVersion
    db = SessionLocal()
    try:
        rows = db.query(ModelVersion).order_by(ModelVersion.id.desc()).limit(limit).all()
        return clean_for_json({"items": [{
            "id": r.id, "version_name": r.version_name, "active": r.active,
            "training_case_count": r.training_case_count,
            "positive_count": r.positive_count, "negative_count": r.negative_count,
            "weight_config": r.weight_config, "performance_summary": r.performance_summary,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        } for r in rows]})
    finally:
        db.close()
