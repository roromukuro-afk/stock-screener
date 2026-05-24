"""20%急騰到達候補 API"""
import threading
from typing import List, Optional, Dict
from datetime import date
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services import surge_20
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


@router.post("/generate-rankings-from-ohlcv")
def generate_rankings_from_ohlcv(req: GenerateRankingsRequest):
    if req.ranking_types:
        out = {}
        for rt in req.ranking_types:
            out[rt] = surge_20.generate_ranking_from_ohlcv(
                rt, market=req.market, snapshot_date=req.snapshot_date, top_n=req.top_n
            )
        return clean_for_json({"status": "ok", "rankings": out})
    r = surge_20.generate_all_rankings(market=req.market, snapshot_date=req.snapshot_date, top_n=req.top_n)
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


@router.post("/detect-events")
def detect_events(req: DetectRequest):
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
    # request param 不要だが BaseModel 受けるため
    return surge_20.extract_pre_features_for_recent_events(limit=req.max_symbols)


# ============== 候補 ==============
@router.post("/build-candidates")
def build_candidates(req: DetectRequest):
    return clean_for_json(surge_20.build_candidates(market=req.market, max_symbols=req.max_symbols))


@router.get("/candidates")
def get_candidates(market: str = "JP", max_symbols: int = 100):
    return clean_for_json(surge_20.build_candidates(market=market, max_symbols=max_symbols))


@router.get("/summary")
def summary():
    return clean_for_json(surge_20.get_summary())
