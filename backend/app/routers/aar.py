"""AAR自動分析・学習データ API"""
import threading
import io
import re
from typing import List, Optional, Dict
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
import pandas as pd

from app.services import aar_analyzer, aar_db, predictor
from app.utils import clean_for_json

router = APIRouter(prefix="/api/aar", tags=["aar"])


# ===== 個別分析 =====
class AnalyzeRequest(BaseModel):
    symbol: str
    market: str = "JP"
    move_date: str
    move_percent: Optional[float] = None
    name: Optional[str] = None
    user_memo: Optional[str] = None
    material_url: Optional[str] = None
    catalyst_text: Optional[str] = None
    news_source: Optional[str] = None
    save: bool = True


@router.post("/analyze")
def analyze_case(req: AnalyzeRequest):
    case = aar_analyzer.analyze_surge_case(
        symbol=req.symbol,
        market=req.market,
        move_date=req.move_date,
        move_percent_user=req.move_percent,
        user_memo=req.user_memo,
        material_url=req.material_url,
        catalyst_text=req.catalyst_text,
        news_source=req.news_source,
        name=req.name,
    )
    if case.get("status") != "ok":
        return clean_for_json({"status": "failed", "error": case.get("error"), "input": req.model_dump()})

    if req.save:
        # 入力ケース → 分析ケース → スナップショット → 特徴ベクトル
        input_id = aar_db.save_input_case(
            symbol=req.symbol, market=req.market, move_date=req.move_date,
            yahoo_symbol=case.get("yahoo_symbol"), name=case.get("name"),
            move_percent_user=req.move_percent, user_memo=req.user_memo,
            material_url=req.material_url, source_file="manual",
        )
        case_id = aar_db.save_analysis_case(input_id, case)
        aar_db.save_snapshots(case_id, case["symbol"], case.get("snapshots", []))
        aar_db.save_feature_vector(case_id, case)
        aar_db.update_input_status(input_id, "analyzed")
        case["case_id"] = case_id

    return clean_for_json(case)


# ===== CSV一括 =====
_csv_progress: Dict = {"running": False, "total": 0, "processed": 0, "saved": 0, "failed": 0, "status": "idle"}
_csv_lock = threading.Lock()


def _process_csv_sync(rows: List[Dict], source_file: str, max_rows: int = 0, save: bool = True):
    """CSV行を順次AAR分析"""
    if max_rows > 0:
        rows = rows[:max_rows]
    with _csv_lock:
        _csv_progress.update({"running": True, "total": len(rows), "processed": 0, "saved": 0, "failed": 0, "status": "running"})

    for row in rows:
        try:
            symbol = str(row.get("symbol") or row.get("yf_symbol") or "").strip()
            yahoo_sym = str(row.get("yf_symbol") or row.get("yahoo_symbol") or symbol).strip()
            market = str(row.get("market") or "JP").strip()
            move_date = str(row.get("move_date") or "").strip()
            move_percent = row.get("move_percent")
            name = str(row.get("name") or "").strip()
            catalyst_text = str(row.get("catalyst") or "").strip()
            news_source = str(row.get("news_source") or "").strip()

            if not symbol or not move_date:
                with _csv_lock:
                    _csv_progress["processed"] += 1
                    _csv_progress["failed"] += 1
                continue

            # 取得用シンボル: yahoo列があればそれを使う
            target_symbol = yahoo_sym if yahoo_sym else symbol
            case = aar_analyzer.analyze_surge_case(
                symbol=target_symbol, market=market, move_date=move_date,
                move_percent_user=float(move_percent) if move_percent not in (None, "", "nan") else None,
                catalyst_text=catalyst_text or None, news_source=news_source or None,
                name=name or None,
            )

            with _csv_lock:
                _csv_progress["processed"] += 1

            if case.get("status") != "ok":
                with _csv_lock:
                    _csv_progress["failed"] += 1
                continue

            if save:
                input_id = aar_db.save_input_case(
                    symbol=target_symbol, market=market, move_date=move_date,
                    yahoo_symbol=case.get("yahoo_symbol"), name=case.get("name"),
                    move_percent_user=case.get("move_percent_user"),
                    source_file=source_file,
                )
                case_id = aar_db.save_analysis_case(input_id, case)
                aar_db.save_snapshots(case_id, case["symbol"], case.get("snapshots", []))
                aar_db.save_feature_vector(case_id, case)
                aar_db.update_input_status(input_id, "analyzed")

            with _csv_lock:
                _csv_progress["saved"] += 1
        except Exception as e:
            with _csv_lock:
                _csv_progress["processed"] += 1
                _csv_progress["failed"] += 1
            print(f"CSV row failed: {e}")

    with _csv_lock:
        _csv_progress.update({"running": False, "status": "completed"})


@router.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...), max_rows: int = 100):
    """CSVをアップロードし、各行をAAR分析+DB保存"""
    if _csv_progress.get("running"):
        raise HTTPException(409, "CSV処理がすでに実行中です")

    content = await file.read()
    filename = file.filename or "uploaded.csv"

    # 文字コード自動判定: BOM付きUTF-8, sjis 両対応
    text = None
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            text = content.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        raise HTTPException(400, "CSVデコード失敗")

    try:
        df = pd.read_csv(io.StringIO(text), dtype=str)
    except Exception as e:
        raise HTTPException(400, f"CSV読込失敗: {e}")

    # カラム名のマッピング(日本語/英語両対応)
    rename_map = {
        "日付": "move_date",
        "市場": "market",
        "銘柄コード": "symbol",
        "yf_シンボル": "yf_symbol",
        "銘柄名": "name",
        "市場区分": "exchange",
        "業種": "sector",
        "前日比(%)": "move_percent",
        "終値": "close",
        "急騰理由": "catalyst",
        "ニュース出典": "news_source",
        "注釈": "memo",
    }
    df = df.rename(columns=rename_map)
    rows = df.to_dict(orient="records")

    t = threading.Thread(target=_process_csv_sync, args=(rows, filename, max_rows, True), daemon=True)
    t.start()
    return {"status": "started", "total_rows_in_file": len(rows), "max_rows_to_process": max_rows, "file": filename}


@router.get("/csv-progress")
def csv_progress():
    with _csv_lock:
        return dict(_csv_progress)


# ===== 学習データ一覧 =====
@router.get("/cases")
def list_cases(limit: int = 200, offset: int = 0, judgement: str = None):
    return clean_for_json(aar_db.list_analysis_cases(limit, offset, judgement))


@router.get("/summary")
def summary():
    return clean_for_json(aar_db.get_aar_summary())


@router.get("/feature-vectors")
def feature_vectors(limit: int = 500):
    return clean_for_json({"items": aar_db.get_feature_vectors_for_matching(limit=limit)})


@router.delete("/cases/{case_id}")
def delete_case(case_id: int):
    ok = aar_db.delete_analysis_case(case_id)
    if not ok:
        raise HTTPException(404, "Case not found")
    return {"deleted": True, "case_id": case_id}


# ===== 現在銘柄予測 =====
class PredictRequest(BaseModel):
    symbol: str
    market: str = "JP"


@router.post("/predict")
def predict(req: PredictRequest):
    return clean_for_json(predictor.predict_symbol(req.symbol, req.market))


class PredictBatchRequest(BaseModel):
    symbols: List[Dict]  # [{symbol, market}]


_predict_progress: Dict = {"running": False, "processed": 0, "total": 0, "status": "idle", "results": []}
_predict_lock = threading.Lock()


def _predict_batch_sync(symbols: List[Dict]):
    from app.services import universe_db
    library = aar_db.get_feature_vectors_for_matching(limit=2000)
    results = []
    with _predict_lock:
        _predict_progress.update({"running": True, "total": len(symbols), "processed": 0, "status": "running", "results": []})

    for s in symbols:
        sym = s.get("symbol")
        market = s.get("market", "JP")
        try:
            current = predictor.compute_current_features(sym, market)
            if current.get("status") != "ok":
                with _predict_lock:
                    _predict_progress["processed"] += 1
                continue
            pred = predictor.match_against_library(current, library, top_k=3)
            pred["symbol"] = sym
            pred["market"] = market
            pred["name"] = s.get("name", sym)
            results.append(pred)
        except Exception:
            pass
        with _predict_lock:
            _predict_progress["processed"] += 1

    with _predict_lock:
        _predict_progress.update({"running": False, "status": "completed", "results": results})


@router.post("/predict-current")
def predict_current(req: PredictBatchRequest):
    if _predict_progress.get("running"):
        raise HTTPException(409, "予測実行中")
    t = threading.Thread(target=_predict_batch_sync, args=(req.symbols,), daemon=True)
    t.start()
    return {"status": "started", "count": len(req.symbols)}


@router.get("/patterns")
def list_patterns():
    """pattern_library の seed パターン一覧"""
    from app.database import SessionLocal
    from app.models.models import PatternLibrary
    db = SessionLocal()
    try:
        rows = db.query(PatternLibrary).all()
        return clean_for_json({
            "total": len(rows),
            "items": [
                {
                    "id": r.id,
                    "pattern_name": r.pattern_name,
                    "pattern_category": r.pattern_category,
                    "description": r.description,
                    "required_conditions": r.required_conditions,
                    "positive_conditions": r.positive_conditions,
                    "negative_conditions": r.negative_conditions,
                    "exclusion_conditions": r.exclusion_conditions,
                    "confidence_weight": r.confidence_weight,
                } for r in rows
            ]
        })
    finally:
        db.close()


@router.get("/predict-progress")
def predict_progress():
    with _predict_lock:
        return clean_for_json(dict(_predict_progress))
