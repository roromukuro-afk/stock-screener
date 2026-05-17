from fastapi import APIRouter, HTTPException
from app.services.price_fetcher import get_stock_data, get_stock_info, get_usd_jpy
from app.services.analyzer import calc_indicators, judge_volume_cycle, judge_chart_cycle, classify_archetype, calc_score, build_warning_flags, generate_ai_comment
from app.services.exporter import generate_aar_text
from app.services.screener import get_progress
from app.utils import clean_for_json

router = APIRouter(prefix="/api/stocks", tags=["stocks"])


@router.get("/{symbol}")
def get_stock(symbol: str):
    progress = get_progress()
    results = progress.get("results", [])
    for r in results:
        if r["symbol"] == symbol:
            return clean_for_json(r)

    # リアルタイム取得
    df = get_stock_data(symbol, period="3mo", market=("JP" if ".T" in symbol else "US"))
    if df is None:
        raise HTTPException(status_code=404, detail=f"銘柄 {symbol} のデータが取得できません")
    info = get_stock_info(symbol)
    indicators = calc_indicators(df)
    fx_rate = get_usd_jpy()
    currency = "JPY" if ".T" in symbol else "USD"
    current_price = float(df["close"].iloc[-1])
    jpy_price = current_price if currency == "JPY" else current_price * fx_rate

    vol_cycle = judge_volume_cycle(df, indicators)
    chart_cycle = judge_chart_cycle(indicators)
    archetypes = classify_archetype(indicators, vol_cycle, chart_cycle, "材料不明")
    score_data = calc_score(indicators, vol_cycle, chart_cycle, "材料不明", jpy_price)
    warning_flags = build_warning_flags(indicators, vol_cycle, chart_cycle, jpy_price)
    ai_comment = generate_ai_comment(
        info.get("name", symbol), indicators, vol_cycle, chart_cycle,
        "材料不明", score_data["total_score"], score_data["classification"], archetypes, warning_flags
    )

    return clean_for_json({
        "symbol": symbol,
        "name": info.get("name", symbol),
        "market": "JP" if ".T" in symbol else "US",
        "currency": currency,
        "price": round(current_price, 4),
        "jpy_price": round(jpy_price, 2),
        "fx_rate": fx_rate,
        **indicators,
        "volume_cycle_state": vol_cycle,
        "chart_cycle_state": chart_cycle,
        **archetypes,
        **score_data,
        "warning_flags": warning_flags,
        "ai_comment": ai_comment,
    })


@router.get("/{symbol}/chart")
def get_stock_chart(symbol: str, period: str = "3mo"):
    df = get_stock_data(symbol, period=period, market=("JP" if ".T" in symbol else "US"))
    if df is None:
        raise HTTPException(status_code=404, detail=f"チャートデータが取得できません: {symbol}")

    indicators = calc_indicators(df)

    records = df[["date", "open", "high", "low", "close", "volume"]].to_dict(orient="records")
    ma5 = float(indicators.get("ma5") or 0)
    ma25 = float(indicators.get("ma25") or 0)
    ma75 = float(indicators.get("ma75") or 0)
    ma200 = float(indicators.get("ma200") or 0)

    # MAシリーズを日付ごとに計算
    closes = df["close"].values.tolist()
    dates = df["date"].values.tolist()

    def rolling_ma(arr, n):
        result = []
        for i in range(len(arr)):
            if i >= n - 1:
                result.append(round(sum(arr[i-n+1:i+1]) / n, 4))
            else:
                result.append(None)
        return result

    ma5_series = rolling_ma(closes, 5)
    ma25_series = rolling_ma(closes, 25)
    ma75_series = rolling_ma(closes, 75)
    ma200_series = rolling_ma(closes, 200)

    chart_data = []
    for i, rec in enumerate(records):
        chart_data.append({
            **rec,
            "ma5": ma5_series[i],
            "ma25": ma25_series[i],
            "ma75": ma75_series[i],
            "ma200": ma200_series[i],
        })

    return clean_for_json({
        "symbol": symbol,
        "period": period,
        "support_line": indicators.get("support_line"),
        "resistance_line": indicators.get("resistance_line"),
        "data": chart_data,
    })


@router.get("/{symbol}/aar")
def get_stock_aar(symbol: str):
    progress = get_progress()
    results = progress.get("results", [])
    result = next((r for r in results if r["symbol"] == symbol), None)
    if not result:
        raise HTTPException(status_code=404, detail="スクリーニング結果がありません。先にスクリーニングを実行してください。")
    aar_text = generate_aar_text(result)
    return {"symbol": symbol, "aar_text": aar_text}
