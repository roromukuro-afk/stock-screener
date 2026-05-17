from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
from app.services.screener import get_progress
from app.services.price_fetcher import get_stock_data
import numpy as np

router = APIRouter(prefix="/api/backtest", tags=["backtest"])

_backtest_results: List[dict] = []


class BacktestRequest(BaseModel):
    symbols: Optional[List[str]] = None


@router.post("/run")
def run_backtest(req: BacktestRequest):
    global _backtest_results
    p = get_progress()
    results = p.get("results", [])

    if req.symbols:
        targets = [r for r in results if r["symbol"] in req.symbols]
    else:
        targets = [r for r in results if r.get("classification") in ["採用候補", "条件付き候補"]]

    _backtest_results = []
    for r in targets:
        symbol = r["symbol"]
        screen_date = r.get("date", "")
        screen_price = r.get("price", 0)

        df = get_stock_data(symbol, period="6mo")
        if df is None or len(df) < 5:
            continue

        closes = df["close"].values.tolist()
        if screen_price <= 0:
            continue

        def get_return(days):
            idx = min(days, len(closes) - 1)
            return round((closes[idx] - closes[0]) / closes[0] * 100, 2) if closes[0] > 0 else None

        r1 = get_return(1)
        r3 = get_return(3)
        r5 = get_return(5)
        r10 = get_return(10)
        r20 = get_return(20)

        max_gain = round(max((c - closes[0]) / closes[0] * 100 for c in closes), 2) if closes else None
        max_dd = round(min((c - closes[0]) / closes[0] * 100 for c in closes), 2) if closes else None
        hit_20 = max_gain is not None and max_gain >= 20

        _backtest_results.append({
            "symbol": symbol,
            "name": r.get("name", symbol),
            "screen_date": screen_date,
            "screen_price": screen_price,
            "classification": r.get("classification"),
            "total_score": r.get("total_score"),
            "result_after_1d": r1,
            "result_after_3d": r3,
            "result_after_5d": r5,
            "result_after_10d": r10,
            "result_after_20d": r20,
            "max_gain": max_gain,
            "max_drawdown": max_dd,
            "hit_20_percent": hit_20,
        })

    return {"message": f"{len(_backtest_results)}件のバックテストを実行しました", "count": len(_backtest_results)}


@router.get("/results")
def get_backtest_results():
    return {"results": _backtest_results, "total": len(_backtest_results)}
