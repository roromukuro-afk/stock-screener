"""5〜20営業日以内に +20%到達を狙う候補を見つけるエンジン

旧目的「明日上がる株」ではなく、
新目的「数日〜1か月以内に +20%以上上昇する可能性がある銘柄を事前に見つける」。

主機能:
  1. OHLCVから日次/3日/5日/1週/10日/20日/1月の上昇率ランキングを自動生成
  2. 過去5年データから +20%到達イベント (期間別) を検出 + 1日急騰検出
  3. 到達イベントから T-20/T-10/T-5/T-3/T-1/T0 の特徴量を抽出
  4. その特徴量に類似した「今」の銘柄を 20%到達候補として生成
"""
import math
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.database import SessionLocal
from app.models.models import (
    HistoricalOHLCV, Surge20Event, Surge20PreFeature, Surge20NegativeCase,
    SurgeRankingSnapshot, SurgeRankingItem,
)
from app.services import universe_db, training_builder


RELATIVE_DAYS = [
    ("T-20", -20),
    ("T-10", -10),
    ("T-5", -5),
    ("T-3", -3),
    ("T-1", -1),
    ("T0", 0),
]

RANKING_WINDOWS = {
    "one_day_gain": 1,
    "three_day_gain": 3,
    "five_day_gain": 5,
    "one_week_gain": 5,
    "ten_day_gain": 10,
    "twenty_day_gain": 20,
    "one_month_gain": 22,
}


def _clean_float(v) -> Optional[float]:
    try:
        if v is None: return None
        f = float(v)
        if math.isnan(f) or math.isinf(f): return None
        return f
    except (TypeError, ValueError):
        return None


def _list_history(symbol: str) -> Optional[pd.DataFrame]:
    db: Session = SessionLocal()
    try:
        rows = (db.query(HistoricalOHLCV)
                .filter(HistoricalOHLCV.symbol == symbol)
                .order_by(HistoricalOHLCV.date).all())
        if not rows:
            return None
        return pd.DataFrame([{
            "date": r.date, "open": r.open, "high": r.high,
            "low": r.low, "close": r.close, "volume": r.volume,
        } for r in rows])
    finally:
        db.close()


# ============== ランキング自動生成 ==============
def generate_ranking_from_ohlcv(
    ranking_type: str,
    market: str = "JP",
    snapshot_date: Optional[str] = None,
    top_n: int = 100,
    max_universe: int = 500,
) -> Dict:
    """OHLCVから指定期間のgain rankingを生成し、surge_ranking_snapshots/items に保存

    max_universe: Render Free対策で対象銘柄数を制限 (デフォルト500)
    """
    window = RANKING_WINDOWS.get(ranking_type)
    if window is None:
        return {"status": "failed", "error": f"unknown ranking_type {ranking_type}"}
    if snapshot_date is None:
        snapshot_date = date.today().isoformat()

    # 対象 universe 銘柄
    syms = universe_db.list_eligible_yahoo_symbols(
        markets=[market] if market != "ALL" else ["JP", "US"],
        max_count=max_universe,
        include_adr=True,
    )

    results = []
    for s in syms:
        sym = s["yahoo_symbol"]
        df = _list_history(sym)
        if df is None or len(df) < window + 1:
            continue
        df = df.sort_values("date").reset_index(drop=True)

        # snapshot_date 以下で最新行
        df_until = df[df["date"].astype(str) <= snapshot_date]
        if len(df_until) < window + 1:
            continue
        curr = df_until.iloc[-1]
        past = df_until.iloc[-1 - window]
        try:
            cp = float(curr["close"])
            sp = float(past["close"])
        except (TypeError, ValueError):
            continue
        if sp <= 0 or math.isnan(cp) or math.isnan(sp):
            continue
        gain = (cp - sp) / sp * 100
        if math.isnan(gain) or math.isinf(gain):
            continue
        vol = _clean_float(curr.get("volume"))
        results.append({
            "symbol": sym,
            "yahoo_symbol": sym,
            "name": s.get("name") or sym,
            "market": s.get("market") or market,
            "current_price": cp,
            "start_price": sp,
            "calculated_gain_percent": round(gain, 3),
            "volume": vol,
            "turnover": round(cp * vol, 2) if vol else None,
            "captured_at": str(curr["date"]),
        })

    # 降順
    results.sort(key=lambda x: x["calculated_gain_percent"] or 0, reverse=True)
    top = results[:top_n]

    # 保存
    db: Session = SessionLocal()
    try:
        snap = SurgeRankingSnapshot(
            ranking_type=ranking_type,
            market=market,
            snapshot_date=snapshot_date,
            source_name=f"ohlcv_auto_{ranking_type}",
            auto_generated=True,
            imported_by_user=False,
            total_items=len(top),
            calculation_method="ohlcv_close_to_close",
        )
        db.add(snap); db.flush()
        snap_id = snap.id

        for idx, r in enumerate(top, 1):
            item = SurgeRankingItem(
                snapshot_id=snap_id,
                symbol=r["symbol"],
                yahoo_symbol=r["yahoo_symbol"],
                name=r["name"],
                market=r["market"],
                rank=idx,
                current_price=r["current_price"],
                start_price=r["start_price"],
                calculated_gain_percent=r["calculated_gain_percent"],
                volume=r["volume"],
                turnover=r["turnover"],
                verified_by_ohlcv=True,
                captured_at=r["captured_at"],
            )
            db.add(item)
        db.commit()
    finally:
        db.close()

    return {
        "status": "ok",
        "snapshot_id": snap_id,
        "ranking_type": ranking_type,
        "market": market,
        "snapshot_date": snapshot_date,
        "total_items": len(top),
        "top_3": top[:3],
    }


def generate_all_rankings(market: str = "JP", snapshot_date: Optional[str] = None,
                          top_n: int = 100, max_universe: int = 300) -> Dict:
    """1日/3日/5日/1週/10日/20日/1月 を一括生成 (Render Free対策で max_universe=300)"""
    out = {}
    for rt in RANKING_WINDOWS.keys():
        try:
            r = generate_ranking_from_ohlcv(rt, market=market, snapshot_date=snapshot_date,
                                            top_n=top_n, max_universe=max_universe)
            out[rt] = {"snapshot_id": r.get("snapshot_id"), "total": r.get("total_items")}
        except Exception as e:
            out[rt] = {"error": str(e)}
    return {"status": "ok", "market": market, "rankings": out}


# ============== +20%到達イベント検出 ==============
def detect_one_day_surges(symbol: str, market: str = "JP", threshold: float = 20.0) -> List[Dict]:
    """1日(close-to-close)で +threshold%以上の急騰日を全期間から検出"""
    df = _list_history(symbol)
    if df is None or len(df) < 2:
        return []
    df = df.sort_values("date").reset_index(drop=True)
    closes = df["close"].astype(float).values
    highs = df["high"].astype(float).values
    volumes = df["volume"].astype(float).values
    events = []
    for i in range(1, len(closes)):
        try:
            prev = float(closes[i - 1]); curr = float(closes[i])
            hi = float(highs[i])
        except (TypeError, ValueError):
            continue
        if math.isnan(prev) or math.isnan(curr) or prev <= 0:
            continue
        close_move = (curr - prev) / prev * 100
        intraday_move = (hi - prev) / prev * 100 if not math.isnan(hi) else None
        if math.isnan(close_move) or close_move < threshold:
            # intraday surge も検出
            if intraday_move is not None and intraday_move >= threshold:
                events.append({
                    "symbol": symbol, "market": market,
                    "event_type": "one_day_intraday_surge_20",
                    "event_start_date": str(df.iloc[i - 1]["date"]),
                    "event_end_date": str(df.iloc[i]["date"]),
                    "start_price": prev, "max_price": hi,
                    "hit_20_date": str(df.iloc[i]["date"]),
                    "max_gain_percent": round(intraday_move, 3),
                    "days_to_hit_20": 1,
                })
            continue
        events.append({
            "symbol": symbol, "market": market,
            "event_type": "one_day_surge_20",
            "event_start_date": str(df.iloc[i - 1]["date"]),
            "event_end_date": str(df.iloc[i]["date"]),
            "start_price": prev, "max_price": curr,
            "hit_20_date": str(df.iloc[i]["date"]),
            "max_gain_percent": round(close_move, 3),
            "days_to_hit_20": 1,
        })
    return events


def detect_multi_day_hit_20(symbol: str, market: str = "JP",
                            windows: List[int] = [3, 5, 10, 20, 22]) -> List[Dict]:
    """T0(基準日)から windows営業日以内に +20%到達したイベントを検出"""
    df = _list_history(symbol)
    if df is None or len(df) < max(windows) + 5:
        return []
    df = df.sort_values("date").reset_index(drop=True)
    closes = df["close"].astype(float).values
    highs = df["high"].astype(float).values
    events = []
    for i in range(len(closes) - max(windows) - 1):
        try:
            base = float(closes[i])
        except (TypeError, ValueError):
            continue
        if base <= 0 or math.isnan(base):
            continue
        for w in windows:
            if i + w >= len(closes):
                continue
            window_highs = highs[i + 1: i + 1 + w]
            window_highs = [float(h) for h in window_highs if not math.isnan(float(h))]
            if not window_highs:
                continue
            max_hi = max(window_highs)
            max_gain = (max_hi - base) / base * 100
            if max_gain >= 20.0:
                hit_idx = i + 1
                for k, h in enumerate(window_highs):
                    if (h - base) / base * 100 >= 20.0:
                        hit_idx = i + 1 + k
                        break
                # event_type を期間別
                if w <= 3: et = "hit_20_within_3d"
                elif w <= 5: et = "hit_20_within_5d"
                elif w <= 10: et = "hit_20_within_10d"
                elif w <= 20: et = "hit_20_within_20d"
                else: et = "hit_20_within_1m"
                events.append({
                    "symbol": symbol, "market": market,
                    "event_type": et,
                    "event_start_date": str(df.iloc[i]["date"]),
                    "event_end_date": str(df.iloc[i + w]["date"]),
                    "hit_20_date": str(df.iloc[hit_idx]["date"]),
                    "days_to_hit_20": hit_idx - i,
                    "start_price": base,
                    "max_price": float(max_hi),
                    "max_gain_percent": round(max_gain, 3),
                })
                break  # 最短windowで1件記録
    return events


def _save_surge_events(events: List[Dict], source_type: str = "detected_from_ohlcv") -> int:
    saved = 0
    for raw in events:
        # 重複: same symbol + event_start_date + event_type
        db = SessionLocal()
        try:
            exists = (db.query(Surge20Event)
                      .filter(Surge20Event.symbol == raw["symbol"])
                      .filter(Surge20Event.event_start_date == raw["event_start_date"])
                      .filter(Surge20Event.event_type == raw["event_type"])
                      .first())
            if exists:
                continue
            row = Surge20Event(
                symbol=raw["symbol"], market=raw.get("market"),
                yahoo_symbol=raw.get("yahoo_symbol", raw["symbol"]),
                name=raw.get("name"),
                event_type=raw["event_type"],
                event_start_date=raw["event_start_date"],
                event_end_date=raw.get("event_end_date"),
                hit_20_date=raw.get("hit_20_date"),
                days_to_hit_20=raw.get("days_to_hit_20"),
                start_price=_clean_float(raw.get("start_price")),
                max_price=_clean_float(raw.get("max_price")),
                max_gain_percent=_clean_float(raw.get("max_gain_percent")),
                max_drawdown_before_hit=_clean_float(raw.get("max_drawdown_before_hit")),
                source_type=source_type,
                source_snapshot_id=raw.get("source_snapshot_id"),
                material_confirmed=False,
                catalyst_category="材料不明",
            )
            db.add(row); db.commit()
            saved += 1
        except Exception as e:
            db.rollback()
            print(f"save surge_20_event failed {raw.get('symbol')}: {e}")
        finally:
            db.close()
    return saved


def detect_events_for_universe(market: str = "JP", max_symbols: int = 100) -> Dict:
    """ユニバース全体で1日急騰 + 期間内+20%到達イベントを検出"""
    syms = universe_db.list_eligible_yahoo_symbols(
        markets=[market], max_count=max_symbols, include_adr=True
    )
    all_events = []
    for s in syms:
        sym = s["yahoo_symbol"]
        try:
            all_events.extend(detect_one_day_surges(sym, s.get("market") or market))
            all_events.extend(detect_multi_day_hit_20(sym, s.get("market") or market))
        except Exception as e:
            print(f"detect events failed {sym}: {e}")
    saved = _save_surge_events(all_events, source_type="detected_from_ohlcv")
    return {
        "status": "ok",
        "universe_size": len(syms),
        "events_detected": len(all_events),
        "events_saved_new": saved,
    }


# ============== T-X 特徴量抽出 ==============
def extract_pre_features(event_id: int) -> int:
    """surge_20_event の T-20/T-10/T-5/T-3/T-1/T0 特徴量を抽出"""
    db = SessionLocal()
    try:
        event = db.query(Surge20Event).filter(Surge20Event.id == event_id).first()
        if not event:
            return 0
    finally:
        db.close()
    df = _list_history(event.symbol)
    if df is None or len(df) < 25:
        return 0
    df = df.sort_values("date").reset_index(drop=True)
    # T0 = event_start_date
    match = df.index[df["date"].astype(str) == event.event_start_date]
    if len(match) == 0:
        return 0
    t0_idx = int(match[0])

    saved = 0
    for label, offset in RELATIVE_DAYS:
        target_idx = t0_idx + offset
        if target_idx < 1 or target_idx >= len(df):
            continue
        # T-1までの特徴量を抽出 (training_builder._calc_t1_features と同じロジック流用)
        try:
            feats = training_builder._calc_t1_features(df, target_idx + 1)  # +1で「target_idxまでで計算」
        except Exception:
            feats = None
        if not feats:
            continue
        asof_date = str(df.iloc[target_idx]["date"])

        d = SessionLocal()
        try:
            exists = (d.query(Surge20PreFeature)
                      .filter(Surge20PreFeature.surge_event_id == event_id)
                      .filter(Surge20PreFeature.relative_day == label)
                      .first())
            if exists:
                continue
            row = Surge20PreFeature(
                surge_event_id=event_id,
                symbol=event.symbol, market=event.market,
                asof_date=asof_date, relative_day=label,
                close=_clean_float(feats.get("close")),
                price_change_1d=_clean_float(feats.get("price_change_1d")),
                price_change_3d=_clean_float(feats.get("price_change_3d")),
                price_change_5d=_clean_float(feats.get("price_change_5d")),
                price_change_10d=_clean_float(feats.get("price_change_5d")),  # 近似
                price_change_20d=_clean_float(feats.get("price_change_20d")),
                volume_ratio_5d=_clean_float(feats.get("volume_ratio_5d")),
                volume_ratio_20d=_clean_float(feats.get("volume_ratio_20d")),
                ma5=_clean_float(feats.get("ma5")),
                ma25=_clean_float(feats.get("ma25")),
                ma75=_clean_float(feats.get("ma75")),
                ma200=_clean_float(feats.get("ma200")),
                ma25_deviation=_clean_float(feats.get("ma25_deviation")),
                support_line=_clean_float(feats.get("support_line")),
                resistance_line=_clean_float(feats.get("resistance_line")),
                support_distance=_clean_float(feats.get("support_distance")),
                resistance_upside=_clean_float(feats.get("resistance_upside")),
                range_position=_clean_float(feats.get("range_position")),
                high_close_flag=bool(feats.get("high_close_flag")),
                breakout_flag=bool(feats.get("range_break_flag")),
                squeeze_flag=bool(feats.get("squeeze_flag")),
                reaccumulation_flag=bool(feats.get("reaccumulation_flag")),
                selling_exhaustion_flag=bool(feats.get("selling_exhaustion_flag")),
                pre_breakout_flag=bool(feats.get("pre_breakout_flag")),
                overextension_score=_clean_float(feats.get("overextension_score")),
                liquidity_score=_clean_float(feats.get("liquidity_score")),
                catalyst_quality_score=0.0,
                catalyst_category="unknown",
                material_confirmed=False,
            )
            d.add(row); d.commit()
            saved += 1
        except Exception as e:
            d.rollback()
            print(f"save pre_feature failed event_id={event_id} {label}: {e}")
        finally:
            d.close()
    return saved


def extract_pre_features_for_recent_events(limit: int = 100) -> Dict:
    db = SessionLocal()
    try:
        events = (db.query(Surge20Event)
                  .order_by(Surge20Event.id.desc())
                  .limit(limit).all())
        event_ids = [e.id for e in events]
    finally:
        db.close()

    total_saved = 0
    for eid in event_ids:
        try:
            total_saved += extract_pre_features(eid)
        except Exception as e:
            print(f"extract_pre_features failed {eid}: {e}")
    return {"status": "ok", "processed_events": len(event_ids), "features_created": total_saved}


# ============== negative case生成 ==============
def generate_negative_cases_for_symbol(symbol: str, market: str, max_cases: int = 30) -> int:
    """positiveに類似(出来高増/ブレイク気配)なのに+20%未達のケースを生成"""
    df = _list_history(symbol)
    if df is None or len(df) < 80:
        return 0
    df = df.sort_values("date").reset_index(drop=True)

    db = SessionLocal()
    try:
        # 既存surge event_start_dateを取得 (positive近傍を避ける)
        positive_dates = {
            d[0] for d in db.query(Surge20Event.event_start_date)
            .filter(Surge20Event.symbol == symbol).all()
        }
    finally:
        db.close()

    closes = df["close"].astype(float).values
    highs = df["high"].astype(float).values
    volumes = df["volume"].astype(float).values

    cases = []
    # 30日おきにサンプリング、最低60日経過
    for i in range(60, len(closes) - 22, 30):
        date_str = str(df.iloc[i]["date"])
        # positive近傍 (±5営業日) はスキップ
        skip = False
        for pd_str in positive_dates:
            if abs((datetime.strptime(date_str, "%Y-%m-%d") - datetime.strptime(pd_str, "%Y-%m-%d")).days) < 5:
                skip = True
                break
        if skip:
            continue

        # T-1相当特徴量
        try:
            feats = training_builder._calc_t1_features(df, i)
        except Exception:
            continue
        if not feats:
            continue

        # positiveっぽい兆候があるか
        is_breakout_like = (
            bool(feats.get("pre_breakout_flag")) or
            bool(feats.get("prior_big_volume_flag")) or
            (feats.get("volume_ratio_20d") or 0) >= 1.5 or
            (feats.get("range_position") or 0) >= 0.8
        )
        if not is_breakout_like:
            continue

        # T+1〜T+20で+20%到達したか
        window_highs = highs[i + 1: i + 21]
        try:
            window_highs = [float(h) for h in window_highs if not math.isnan(float(h))]
        except Exception:
            window_highs = []
        if not window_highs:
            continue
        base = float(closes[i])
        if base <= 0:
            continue
        max_hi = max(window_highs)
        max_gain = (max_hi - base) / base * 100
        if max_gain >= 20.0:
            continue  # positiveなのでスキップ
        hit_20 = False

        # failure_reason 推定
        overext = feats.get("overextension_score") or 0
        upside = feats.get("resistance_upside") or 0
        pc5 = feats.get("price_change_5d") or 0
        vol_r = feats.get("volume_ratio_20d") or 0
        liquidity = feats.get("liquidity_score") or 0

        if overext >= 60 or pc5 >= 30:
            reason = "overextended"
        elif upside < 10:
            reason = "resistance_too_close"
        elif vol_r >= 2.0 and max_gain < 5:
            reason = "volume_spike_failed"
        elif liquidity < 30:
            reason = "low_liquidity"
        elif feats.get("pre_breakout_flag") and max_gain < 5:
            reason = "looked_like_breakout_but_failed"
        else:
            reason = "material_weak"

        cases.append({
            "symbol": symbol, "market": market,
            "asof_date": date_str,
            "reason": reason,
            "max_gain_next_20d": round(max_gain, 3),
            "hit_20_next_20d": False,
            "failure_reason": f"max_gain={max_gain:.1f}% overext={overext:.0f} upside={upside:.1f}%",
        })
        if len(cases) >= max_cases:
            break

    # DB保存
    saved = 0
    for c in cases:
        d = SessionLocal()
        try:
            existing = (d.query(Surge20NegativeCase)
                        .filter(Surge20NegativeCase.symbol == c["symbol"])
                        .filter(Surge20NegativeCase.asof_date == c["asof_date"])
                        .first())
            if existing:
                continue
            d.add(Surge20NegativeCase(**c))
            d.commit()
            saved += 1
        except Exception as e:
            d.rollback()
            print(f"save negative case failed {c['symbol']} {c['asof_date']}: {e}")
        finally:
            d.close()
    return saved


def generate_negative_cases_for_universe(market: str = "JP", max_symbols: int = 100,
                                          max_per_symbol: int = 20) -> Dict:
    syms = universe_db.list_eligible_yahoo_symbols(
        markets=[market], max_count=max_symbols, include_adr=True
    )
    total = 0
    for s in syms:
        try:
            total += generate_negative_cases_for_symbol(
                s["yahoo_symbol"], s.get("market") or market, max_cases=max_per_symbol
            )
        except Exception as e:
            print(f"negative gen failed {s['yahoo_symbol']}: {e}")
    return {"status": "ok", "universe_size": len(syms), "negative_cases_created": total}


# ============== 重複整理 ==============
def consolidate_duplicate_events(min_gap_days: int = 5) -> Dict:
    """同一symbol で event_start_date が min_gap_days 以内のイベントを整理。
    優先順位: one_day_surge_20 > hit_20_within_3d > 5d > 10d > 20d > 1m
    """
    priority = {
        "one_day_surge_20": 0,
        "one_day_intraday_surge_20": 1,
        "hit_20_within_3d": 2,
        "hit_20_within_5d": 3,
        "hit_20_within_10d": 4,
        "hit_20_within_20d": 5,
        "hit_20_within_1m": 6,
    }
    db = SessionLocal()
    try:
        # 銘柄ごとに event を取得
        symbols = [s[0] for s in db.query(Surge20Event.symbol).distinct().all()]
        deleted_total = 0
        for sym in symbols:
            evs = (db.query(Surge20Event)
                   .filter(Surge20Event.symbol == sym)
                   .order_by(Surge20Event.event_start_date).all())
            if len(evs) < 2:
                continue
            # 日付ごとにグループ化 (min_gap_days以内をまとめる)
            evs_with_dt = []
            for e in evs:
                try:
                    dt = datetime.strptime(e.event_start_date, "%Y-%m-%d")
                    evs_with_dt.append((dt, e))
                except Exception:
                    pass
            evs_with_dt.sort(key=lambda x: x[0])

            groups = []
            current_group = [evs_with_dt[0]]
            for dt, e in evs_with_dt[1:]:
                if (dt - current_group[-1][0]).days <= min_gap_days:
                    current_group.append((dt, e))
                else:
                    groups.append(current_group)
                    current_group = [(dt, e)]
            groups.append(current_group)

            for g in groups:
                if len(g) < 2:
                    continue
                # 優先順位で残すものを選ぶ
                g.sort(key=lambda x: priority.get(x[1].event_type, 99))
                keep_id = g[0][1].id
                for _, e in g[1:]:
                    if e.id != keep_id:
                        db.delete(e)
                        deleted_total += 1
            db.commit()
        return {"status": "ok", "deleted_duplicate_events": deleted_total, "symbols_checked": len(symbols)}
    finally:
        db.close()


# ============== サマリ ==============
def get_summary() -> Dict:
    db = SessionLocal()
    try:
        snaps = db.query(SurgeRankingSnapshot).count()
        items = db.query(SurgeRankingItem).count()
        events = db.query(Surge20Event).count()
        events_by_type = dict(
            db.query(Surge20Event.event_type, func.count(Surge20Event.id))
              .group_by(Surge20Event.event_type).all()
        )
        pre_feats = db.query(Surge20PreFeature).count()
        pre_feats_by_rel = dict(
            db.query(Surge20PreFeature.relative_day, func.count(Surge20PreFeature.id))
              .group_by(Surge20PreFeature.relative_day).all()
        )
        negatives = db.query(Surge20NegativeCase).count()
        negatives_by_reason = dict(
            db.query(Surge20NegativeCase.reason, func.count(Surge20NegativeCase.id))
              .group_by(Surge20NegativeCase.reason).all()
        )
        unique_symbols_events = db.query(Surge20Event.symbol).distinct().count()
        unique_symbols_features = db.query(Surge20PreFeature.symbol).distinct().count()
        events_by_market = dict(
            db.query(Surge20Event.market, func.count(Surge20Event.id))
              .group_by(Surge20Event.market).all()
        )
        pos_count = sum(events_by_type.values()) if 'events_by_type' in dir() else events
        ratio = round(negatives / max(1, pos_count), 3) if pos_count > 0 else None
        recent_snaps = (db.query(SurgeRankingSnapshot)
                        .order_by(SurgeRankingSnapshot.id.desc()).limit(10).all())
        return {
            "ranking_snapshots": snaps,
            "ranking_items": items,
            "surge_20_events": events,
            "unique_symbols_with_events": unique_symbols_events,
            "events_by_type": events_by_type,
            "events_by_market": events_by_market,
            "pre_features": pre_feats,
            "pre_features_by_relative_day": pre_feats_by_rel,
            "unique_symbols_with_features": unique_symbols_features,
            "negative_cases": negatives,
            "negative_cases_by_reason": negatives_by_reason,
            "positive_negative_ratio": ratio,
            "recent_snapshots": [
                {"id": s.id, "ranking_type": s.ranking_type, "market": s.market,
                 "snapshot_date": s.snapshot_date, "total_items": s.total_items,
                 "auto_generated": s.auto_generated,
                 "created_at": s.created_at.isoformat() if s.created_at else None}
                for s in recent_snaps
            ],
        }
    finally:
        db.close()


def list_recent_snapshots(limit: int = 20) -> List[Dict]:
    db = SessionLocal()
    try:
        rows = (db.query(SurgeRankingSnapshot)
                .order_by(SurgeRankingSnapshot.id.desc()).limit(limit).all())
        return [{
            "id": s.id, "ranking_type": s.ranking_type, "market": s.market,
            "snapshot_date": s.snapshot_date, "total_items": s.total_items,
            "auto_generated": s.auto_generated,
            "imported_by_user": s.imported_by_user,
            "calculation_method": s.calculation_method,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        } for s in rows]
    finally:
        db.close()


def list_snapshot_items(snapshot_id: int, limit: int = 100) -> List[Dict]:
    db = SessionLocal()
    try:
        rows = (db.query(SurgeRankingItem)
                .filter(SurgeRankingItem.snapshot_id == snapshot_id)
                .order_by(SurgeRankingItem.rank).limit(limit).all())
        return [{
            "id": r.id, "symbol": r.symbol, "name": r.name, "market": r.market,
            "rank": r.rank, "current_price": r.current_price,
            "start_price": r.start_price,
            "calculated_gain_percent": r.calculated_gain_percent,
            "imported_gain_percent": r.imported_gain_percent,
            "gain_percent_diff": r.gain_percent_diff,
            "volume": r.volume, "turnover": r.turnover,
            "verified_by_ohlcv": r.verified_by_ohlcv,
            "verification_warning": r.verification_warning,
            "captured_at": r.captured_at,
        } for r in rows]
    finally:
        db.close()


def list_recent_events(limit: int = 50, event_type: Optional[str] = None) -> List[Dict]:
    db = SessionLocal()
    try:
        q = db.query(Surge20Event)
        if event_type:
            q = q.filter(Surge20Event.event_type == event_type)
        rows = q.order_by(Surge20Event.id.desc()).limit(limit).all()
        return [{
            "id": e.id, "symbol": e.symbol, "name": e.name, "market": e.market,
            "event_type": e.event_type,
            "event_start_date": e.event_start_date,
            "hit_20_date": e.hit_20_date,
            "days_to_hit_20": e.days_to_hit_20,
            "start_price": e.start_price, "max_price": e.max_price,
            "max_gain_percent": e.max_gain_percent,
            "source_type": e.source_type,
            "material_confirmed": e.material_confirmed,
            "catalyst_category": e.catalyst_category,
        } for e in rows]
    finally:
        db.close()


# ============== 20%到達候補生成 (簡易) ==============
def build_candidates(market: str = "JP", max_symbols: int = 200) -> Dict:
    """過去のT-3/T-5 positive pre_features と類似度マッチで候補生成

    実装ポイント: pre_featuresの T-3/T-5 のみを取り出し、現在銘柄のT-1相当と比較。
    """
    from app.services.predictor import _numeric_distance, compute_current_features

    db = SessionLocal()
    try:
        # 全 pre_features を取得 (T-3/T-5を中心に)
        pres = (db.query(Surge20PreFeature)
                .filter(Surge20PreFeature.relative_day.in_(["T-5", "T-3", "T-1"]))
                .limit(2000).all())
        # 比較用形式に変換
        library = [{
            "case_id": p.id,
            "symbol": p.symbol,
            "case_type": "surge_20_positive",
            "t1_volume_ratio_20d": p.volume_ratio_20d,
            "t1_price_change_5d": p.price_change_5d,
            "t1_price_change_20d": p.price_change_20d,
            "t1_ma25_deviation": p.ma25_deviation,
            "t1_resistance_upside": p.resistance_upside,
            "t1_support_distance": p.support_distance,
            "t1_overextension_score": p.overextension_score,
            "label_hit_20_percent": True,
            "relative_day": p.relative_day,
        } for p in pres]
    finally:
        db.close()

    if not library:
        return {"status": "no_library", "message": "先に surge_20_events と pre_features を作成してください"}

    syms = universe_db.list_eligible_yahoo_symbols(
        markets=[market], max_count=max_symbols, include_adr=True,
    )

    candidates = []
    for s in syms:
        sym = s["yahoo_symbol"]
        market_s = s.get("market") or market
        try:
            current = compute_current_features(sym, market_s)
            if current.get("status") != "ok":
                continue
        except Exception:
            continue
        # 類似度上位N件平均
        scored = []
        for c in library:
            dist = _numeric_distance(current, c)
            sim = max(0.0, 1.0 - dist)
            scored.append({"case": c, "similarity": sim})
        scored.sort(key=lambda x: x["similarity"], reverse=True)
        top = scored[:5]
        if not top:
            continue
        avg_sim = sum(x["similarity"] for x in top) / len(top)
        if avg_sim < 0.4:
            continue
        candidates.append({
            "symbol": sym,
            "name": s.get("name"),
            "market": market_s,
            "current_price": current.get("close"),
            "avg_similarity_top5": round(avg_sim, 4),
            "resistance_upside": current.get("t1_resistance_upside"),
            "ma25_deviation": current.get("t1_ma25_deviation"),
            "overextension_score": current.get("t1_overextension_score"),
            "support_distance": current.get("t1_support_distance"),
            "matched_relative_days": [x["case"]["relative_day"] for x in top],
            "matched_past_symbols": [x["case"]["symbol"] for x in top],
        })

    candidates.sort(key=lambda x: x["avg_similarity_top5"], reverse=True)
    return {
        "status": "ok",
        "market": market,
        "universe_scanned": len(syms),
        "candidates_count": len(candidates),
        "candidates_top50": candidates[:50],
    }
