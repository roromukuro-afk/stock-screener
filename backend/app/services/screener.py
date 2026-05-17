"""全銘柄スクリーニングサービス"""
import asyncio
from datetime import datetime, date
from typing import Dict, List, Optional, Any
import threading

from app.services.universe import get_universe
from app.services.price_fetcher import (
    get_stock_data, get_stock_info, get_usd_jpy, set_sample_mode,
    get_stock_quote_with_freshness, is_sample_mode,
)
from app.services.analyzer import (
    calc_indicators, judge_volume_cycle, judge_chart_cycle,
    classify_archetype, calc_score, build_warning_flags, generate_ai_comment
)
from app.services.freshness import assess_freshness
from app.db_repo import save_screening_run
from app.services import universe_db


_screening_progress: Dict[str, Any] = {
    "running": False,
    "total": 0,
    "processed": 0,
    "failed": 0,
    "results": [],
    "exclusions": [],
    "status": "idle",
    "started_at": None,
    "finished_at": None,
    "error": None,
}

_lock = threading.Lock()


def get_progress() -> Dict:
    with _lock:
        return dict(_screening_progress)


def run_screening_background(params: Dict):
    thread = threading.Thread(target=_run_screening, args=(params,), daemon=True)
    thread.start()


def _run_screening(params: Dict):
    global _screening_progress
    with _lock:
        _screening_progress.update({
            "running": True,
            "total": 0,
            "processed": 0,
            "failed": 0,
            "results": [],
            "exclusions": [],
            "status": "running",
            "started_at": datetime.now().isoformat(),
            "finished_at": None,
            "error": None,
        })

    try:
        markets = params.get("markets", ["JP", "US"])
        include_adr = params.get("include_adr", False)
        use_real = params.get("use_real_data", True)
        price_limit = params.get("price_limit", 3000)
        min_vol_jp = params.get("min_vol_jp", 30000)
        min_vol_us = params.get("min_vol_us", 100000)
        min_score = params.get("min_score", 0)
        max_symbols = params.get("max_symbols", 0)  # 0 = 制限なし
        use_db_universe = params.get("use_db_universe", True)
        enforce_freshness_gate = params.get("enforce_freshness_gate", True)

        # サンプルモード切り替え
        set_sample_mode(not use_real)

        fx_rate = get_usd_jpy()
        fx_timestamp = datetime.now().isoformat()

        # ユニバース取得: DB優先(eligible only)、空ならフォールバック
        universe = []
        if use_db_universe:
            db_items = universe_db.list_eligible_yahoo_symbols(
                markets=markets, max_count=max_symbols, include_adr=include_adr
            )
            for it in db_items:
                universe.append({
                    "symbol": it["yahoo_symbol"],
                    "name": it["name"],
                    "market": it["market"],
                    "exchange": "",
                    "is_adr": it.get("is_adr", False),
                })
        if not universe:
            universe = get_universe(markets, include_adr, use_real)
            if max_symbols > 0:
                universe = universe[:max_symbols]

        with _lock:
            _screening_progress["total"] = len(universe)

        results = []
        exclusions = []
        today = date.today().isoformat()

        excluded_symbols = set(params.get("excluded_symbols", []))

        for stock in universe:
            symbol = stock["symbol"]
            market = stock.get("market", "JP")
            is_adr = stock.get("is_adr", False)

            with _lock:
                _screening_progress["processed"] += 1

            # 除外リスト確認
            if symbol in excluded_symbols:
                exclusions.append({
                    "symbol": symbol,
                    "name": stock.get("name", symbol),
                    "market": market,
                    "exclude_reason": "除外リスト登録済み",
                    "price": None,
                    "volume": None,
                    "date": today,
                })
                continue

            # 株価取得
            df = get_stock_data(symbol, period="3mo", market=market)
            if df is None or len(df) < 5:
                exclusions.append({
                    "symbol": symbol,
                    "name": stock.get("name", symbol),
                    "market": market,
                    "exclude_reason": "データ取得失敗 (price_fetch_failed)",
                    "freshness_status": "price_fetch_failed",
                    "price": None,
                    "volume": None,
                    "date": today,
                })
                with _lock:
                    _screening_progress["failed"] += 1
                continue

            # 鮮度ゲート: 価格対象日が当該市場の最新営業日かチェック
            last_quote_date = str(df["date"].iloc[-1]) if "date" in df.columns else None
            fresh = assess_freshness(market=market, quote_date=last_quote_date, quote_timestamp=None, data_source="yfinance")

            if enforce_freshness_gate and fresh.get("is_stale") and not is_sample_mode():
                exclusions.append({
                    "symbol": symbol,
                    "name": stock.get("name", symbol),
                    "market": market,
                    "exclude_reason": f"価格データが古い ({fresh.get('stale_reason')})",
                    "freshness_status": fresh.get("freshness_status"),
                    "stale_reason": fresh.get("stale_reason"),
                    "quote_date": last_quote_date,
                    "price": float(df["close"].iloc[-1]) if "close" in df.columns else None,
                    "volume": float(df["volume"].iloc[-1]) if "volume" in df.columns else None,
                    "date": today,
                })
                continue

            current_price = float(df["close"].iloc[-1])
            current_vol = float(df["volume"].iloc[-1]) if "volume" in df.columns else 0

            # 通貨・円換算
            currency = "JPY" if ".T" in symbol else "USD"
            if currency == "JPY":
                jpy_price = current_price
                rate = 1.0
            else:
                jpy_price = current_price * fx_rate
                rate = fx_rate

            # 価格条件
            if jpy_price <= 0:
                exclusions.append({"symbol": symbol, "name": stock.get("name", symbol), "market": market,
                                   "exclude_reason": "価格不明", "price": current_price, "volume": current_vol, "date": today})
                continue
            if jpy_price > price_limit:
                exclusions.append({"symbol": symbol, "name": stock.get("name", symbol), "market": market,
                                   "exclude_reason": "価格条件外", "price": current_price, "volume": current_vol, "date": today})
                continue

            # 流動性チェック
            min_vol = min_vol_jp if market == "JP" else min_vol_us
            vol_avg20 = df["volume"].tail(20).mean() if len(df) >= 20 else df["volume"].mean()
            if vol_avg20 < min_vol:
                exclusions.append({"symbol": symbol, "name": stock.get("name", symbol), "market": market,
                                   "exclude_reason": "出来高不足", "price": current_price, "volume": current_vol, "date": today})
                continue

            # テクニカル指標計算
            indicators = calc_indicators(df)
            if not indicators:
                exclusions.append({"symbol": symbol, "name": stock.get("name", symbol), "market": market,
                                   "exclude_reason": "指標計算失敗", "price": current_price, "volume": current_vol, "date": today})
                continue

            # ハード除外チェック
            ma25_dev = indicators.get("ma25_deviation", 0)
            price_change_20d = indicators.get("price_change_20d", 0)
            upside = indicators.get("upside_to_resistance", 0)
            support_dist = indicators.get("support_distance", 999)

            if ma25_dev >= 80:
                exclusions.append({"symbol": symbol, "name": stock.get("name", symbol), "market": market,
                                   "exclude_reason": "25MA乖離過大(80%以上)", "price": current_price, "volume": current_vol, "date": today})
                continue
            if price_change_20d >= 100:
                exclusions.append({"symbol": symbol, "name": stock.get("name", symbol), "market": market,
                                   "exclude_reason": "短期急騰済み(20日2倍以上)", "price": current_price, "volume": current_vol, "date": today})
                continue
            if upside < 5:
                exclusions.append({"symbol": symbol, "name": stock.get("name", symbol), "market": market,
                                   "exclude_reason": "上値余地不足(5%未満)", "price": current_price, "volume": current_vol, "date": today})
                continue

            # サイクル判定
            vol_cycle = judge_volume_cycle(df, indicators)
            chart_cycle = judge_chart_cycle(indicators)

            # 天井判定
            if vol_cycle == "天井大商い警戒" and chart_cycle == "上がり切り":
                exclusions.append({"symbol": symbol, "name": stock.get("name", symbol), "market": market,
                                   "exclude_reason": "天井大商い・上がり切り", "price": current_price, "volume": current_vol, "date": today})
                continue

            # 材料判定(MVP: 簡易)
            material_status = "材料不明"

            # アーキタイプ分類
            archetypes = classify_archetype(indicators, vol_cycle, chart_cycle, material_status)

            # スコア計算
            score_data = calc_score(indicators, vol_cycle, chart_cycle, material_status, jpy_price, price_limit)
            total_score = score_data["total_score"]
            classification = score_data["classification"]

            # 上値余地20%未満は除外
            if upside < 20:
                classification = "除外対象"

            # 警告フラグ
            warning_flags = build_warning_flags(indicators, vol_cycle, chart_cycle, jpy_price)

            # AIコメント
            ai_comment = generate_ai_comment(
                stock.get("name", symbol), indicators, vol_cycle, chart_cycle,
                material_status, total_score, classification, archetypes, warning_flags
            )

            # 株式情報
            turnover = current_price * current_vol if current_vol else 0
            if currency == "USD":
                turnover_jpy = turnover * fx_rate
            else:
                turnover_jpy = turnover

            result = {
                "symbol": symbol,
                "name": stock.get("name", symbol),
                "market": market,
                "exchange": stock.get("exchange", ""),
                "is_adr": is_adr,
                "date": today,
                "price": round(current_price, 4),
                "currency": currency,
                "jpy_price": round(jpy_price, 2),
                "fx_rate": round(rate, 4),
                "fx_rate_timestamp": fx_timestamp,
                "price_timestamp": datetime.now().isoformat(),
                "quote_date": last_quote_date,
                "freshness_status": fresh.get("freshness_status"),
                "fetched_at_jst": fresh.get("fetched_at_jst"),
                "is_realtime_or_delayed": fresh.get("is_realtime_or_delayed"),
                "data_source": "sample" if is_sample_mode() else "yfinance",
                "volume": current_vol,
                "volume_avg20": round(float(vol_avg20), 0),
                "volume_ratio": indicators.get("volume_ratio", 1.0),
                "turnover": round(turnover, 2),
                "ma5": indicators.get("ma5"),
                "ma25": indicators.get("ma25"),
                "ma75": indicators.get("ma75"),
                "ma200": indicators.get("ma200"),
                "ma25_deviation": indicators.get("ma25_deviation"),
                "recent_high_20": indicators.get("recent_high_20"),
                "recent_low_20": indicators.get("recent_low_20"),
                "support_line": indicators.get("support_line"),
                "resistance_line": indicators.get("resistance_line"),
                "upside_to_resistance": indicators.get("upside_to_resistance"),
                "support_distance": indicators.get("support_distance"),
                "price_change_1d": indicators.get("price_change_1d"),
                "price_change_5d": indicators.get("price_change_5d"),
                "price_change_20d": indicators.get("price_change_20d"),
                "rsi": indicators.get("rsi"),
                "atr": indicators.get("atr"),
                "trend_state": indicators.get("trend_state"),
                "range_state": indicators.get("range_state"),
                "candle_state": indicators.get("candle_state"),
                "chart_pattern_primary": indicators.get("chart_pattern_primary"),
                "chart_pattern_secondary": indicators.get("chart_pattern_secondary"),
                "chart_pattern_warning": indicators.get("chart_pattern_warning"),
                "pattern_confidence": indicators.get("pattern_confidence"),
                "volume_cycle_state": vol_cycle,
                "chart_cycle_state": chart_cycle,
                "material_status": material_status,
                "upside_score": score_data["upside_score"],
                "future_catalyst_score": score_data["future_catalyst_score"],
                "chart_score": score_data["chart_score"],
                "volume_cycle_score": score_data["volume_cycle_score"],
                "material_theme_score": score_data["material_theme_score"],
                "supply_score": score_data["supply_score"],
                "archetype_score": score_data["archetype_score"],
                "risk_management_score": score_data["risk_management_score"],
                "total_score": total_score,
                "classification": classification,
                "main_archetype": archetypes["main_archetype"],
                "sub_archetypes": archetypes["sub_archetypes"],
                "chart_types": archetypes["chart_types"],
                "warning_types": archetypes["warning_types"],
                "warning_flags": warning_flags,
                "exclude_flag": False,
                "exclude_reason": "",
                "ai_comment": ai_comment,
            }
            results.append(result)

        results.sort(key=lambda x: x["total_score"], reverse=True)

        # DBに保存
        try:
            save_screening_run(results, exclusions, markets, include_adr)
        except Exception as e:
            print(f"DB save failed: {e}")

        with _lock:
            _screening_progress.update({
                "running": False,
                "results": results,
                "exclusions": exclusions,
                "status": "completed",
                "finished_at": datetime.now().isoformat(),
            })

    except Exception as e:
        with _lock:
            _screening_progress.update({
                "running": False,
                "status": "error",
                "error": str(e),
                "finished_at": datetime.now().isoformat(),
            })
        raise
