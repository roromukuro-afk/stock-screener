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
import threading
from typing import Dict, List, Optional, Tuple
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np

# ===== 同時実行lock (Render Free単一worker保護) =====
_HEAVY_LOCK = threading.Lock()
_heavy_running = {"task": None, "started_at": None}


def is_heavy_running() -> bool:
    return _heavy_running["task"] is not None


def _acquire_heavy(task_name: str) -> bool:
    """重い処理の排他取得。取れたらTrue。busyならFalse"""
    if not _HEAVY_LOCK.acquire(blocking=False):
        return False
    _heavy_running["task"] = task_name
    _heavy_running["started_at"] = datetime.utcnow().isoformat()
    return True


def _release_heavy():
    _heavy_running["task"] = None
    _heavy_running["started_at"] = None
    try:
        _HEAVY_LOCK.release()
    except RuntimeError:
        pass


def heavy_status() -> Dict:
    return {
        "busy": is_heavy_running(),
        "task": _heavy_running["task"],
        "started_at": _heavy_running["started_at"],
    }
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


# ============== data-quality / orphan処理 ==============
def get_data_quality() -> Dict:
    """orphan pre_features / events_with(without)_features / 警告を返す"""
    db = SessionLocal()
    try:
        event_ids = {e[0] for e in db.query(Surge20Event.id).all()}
        feat_event_ids = [f[0] for f in db.query(Surge20PreFeature.surge_event_id).all()]
        orphan = [eid for eid in feat_event_ids if eid not in event_ids]
        orphan_count = len(orphan)
        total_features = len(feat_event_ids)
        orphan_ratio = round(orphan_count / max(1, total_features), 4)

        events_with_features = (db.query(Surge20PreFeature.surge_event_id).distinct().count())
        # events_with_features - orphan count = 有効eventの中で features を持つ件数
        valid_events_with_features = len({eid for eid in feat_event_ids if eid in event_ids})
        events_without_features = len(event_ids) - valid_events_with_features

        feats_by_rel = dict(
            db.query(Surge20PreFeature.relative_day, func.count(Surge20PreFeature.id))
              .group_by(Surge20PreFeature.relative_day).all()
        )
        events_by_type = dict(
            db.query(Surge20Event.event_type, func.count(Surge20Event.id))
              .group_by(Surge20Event.event_type).all()
        )
        neg_by_reason = dict(
            db.query(Surge20NegativeCase.reason, func.count(Surge20NegativeCase.id))
              .group_by(Surge20NegativeCase.reason).all()
        )

        unique_event_symbols = db.query(Surge20Event.symbol).distinct().count()
        unique_feature_symbols = db.query(Surge20PreFeature.symbol).distinct().count()

        warnings = []
        if orphan_count > 0:
            warnings.append(f"orphan_pre_features: {orphan_count}件 (削除済みevent参照)")
        if events_without_features > len(event_ids) * 0.5:
            warnings.append(f"events_without_features: {events_without_features}件 (features抽出未完了)")
        rel_vals = list(feats_by_rel.values())
        if rel_vals and (max(rel_vals) - min(rel_vals)) / max(1, max(rel_vals)) > 0.3:
            warnings.append("relative_day分布が偏っています")
        neg_count = db.query(Surge20NegativeCase).count()
        if len(event_ids) > 0 and neg_count / len(event_ids) > 10:
            warnings.append(f"negative/event 比率が高すぎ ({round(neg_count/len(event_ids),2)})")
        if len(event_ids) < 50:
            warnings.append(f"positive event が少ない ({len(event_ids)})")

        return {
            "surge_20_events": len(event_ids),
            "pre_features": total_features,
            "orphan_pre_features": orphan_count,
            "orphan_pre_feature_ratio": orphan_ratio,
            "events_with_features": valid_events_with_features,
            "events_without_features": events_without_features,
            "features_by_relative_day": feats_by_rel,
            "events_by_type": events_by_type,
            "negative_cases": neg_count,
            "negative_by_reason": neg_by_reason,
            "unique_event_symbols": unique_event_symbols,
            "unique_feature_symbols": unique_feature_symbols,
            "warnings": warnings,
        }
    finally:
        db.close()


def cleanup_orphan_pre_features() -> Dict:
    """削除済みeventを参照するpre_featuresを削除"""
    db = SessionLocal()
    try:
        event_ids = {e[0] for e in db.query(Surge20Event.id).all()}
        orphan_ids = [f.id for f in db.query(Surge20PreFeature).all()
                      if f.surge_event_id not in event_ids]
        if not orphan_ids:
            return {"status": "ok", "deleted": 0}
        deleted = (db.query(Surge20PreFeature)
                   .filter(Surge20PreFeature.id.in_(orphan_ids))
                   .delete(synchronize_session=False))
        db.commit()
        return {"status": "ok", "deleted": deleted}
    finally:
        db.close()


def get_light_status() -> Dict:
    """高負荷時でも返る軽量status。最小限のCOUNTのみ。

    どこかのCOUNT/テーブルが失敗しても全体を500にしない。
    項目ごとに try/except で fallback し、warnings に記録、status=degraded で200返却。
    """
    from app.models.models import (
        Surge20Candidate, PredictionLog, AutomationError, AutomationLock
    )
    today = date.today().isoformat()
    warnings: List[str] = []
    out: Dict = {
        "status": "ok",
        "active_locks": [],
        "heavy_running": False,
        "heavy_task": None,
        "candidates_today": 0,
        "main_saved_today": 0,
        "watch_saved_today": 0,
        "rejected_watch_saved_today": 0,
        "late_chase_watch_saved_today": 0,
        "open_surge_20_predictions": 0,
        "errors_last_24h": 0,
        "render_safe_to_run": False,
        "warnings": warnings,
    }

    def _short(e: Exception) -> str:
        s = str(e).strip().splitlines()
        return (s[0] if s else type(e).__name__)[:160]

    # heavy状態 (DB不要・最優先)
    try:
        out["heavy_running"] = is_heavy_running()
        out["heavy_task"] = heavy_status().get("task")
    except Exception as e:
        warnings.append(f"heavy_status: {_short(e)}")

    db = None
    try:
        db = SessionLocal()
    except Exception as e:
        warnings.append(f"db_connect: {_short(e)}")
        out["status"] = "degraded"
        return out

    try:
        # 今日のcandidates
        try:
            out["candidates_today"] = (db.query(Surge20Candidate)
                                       .filter(Surge20Candidate.candidate_date == today).count())
        except Exception as e:
            db.rollback(); warnings.append(f"candidates_today: {_short(e)}")

        # 今日のprediction保存 (type別)
        def _count_today(pt):
            try:
                return (db.query(PredictionLog)
                        .filter(PredictionLog.prediction_date == today)
                        .filter(PredictionLog.prediction_type == pt).count())
            except Exception as e:
                db.rollback(); warnings.append(f"pred[{pt}]: {_short(e)}")
                return 0
        out["main_saved_today"] = _count_today("surge_20_prediction")
        out["watch_saved_today"] = _count_today("surge_20_watch_prediction")
        out["rejected_watch_saved_today"] = _count_today("surge_20_rejected_watch")
        out["late_chase_watch_saved_today"] = _count_today("surge_20_late_chase_watch")

        # open surge_20 predictions
        try:
            out["open_surge_20_predictions"] = (db.query(PredictionLog)
                .filter(PredictionLog.prediction_type.in_(SURGE_20_PREDICTION_TYPES))
                .filter(PredictionLog.status == "open").count())
        except Exception as e:
            db.rollback(); warnings.append(f"open_preds: {_short(e)}")

        # active locks
        now = datetime.utcnow()
        active_locks = []
        try:
            for lk in db.query(AutomationLock).all():
                if lk.expires_at and lk.expires_at > now:
                    active_locks.append(lk.lock_key)
        except Exception as e:
            db.rollback(); warnings.append(f"locks: {_short(e)}")
        out["active_locks"] = active_locks

        # errors last 24h
        try:
            err_cutoff = now - timedelta(hours=24)
            out["errors_last_24h"] = (db.query(AutomationError)
                                      .filter(AutomationError.created_at >= err_cutoff).count())
        except Exception as e:
            db.rollback(); warnings.append(f"errors_24h: {_short(e)}")

        # render_safe_to_run: heavy lock + active DB locks がなければ安全
        out["render_safe_to_run"] = (not out["heavy_running"]) and len(active_locks) == 0
        if warnings:
            out["status"] = "degraded"
            out["render_safe_to_run"] = False
        return out
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


# ============== automation_state cursor ==============
def _state_get(key: str, default: str = "0") -> str:
    """automation_settings を cursor として流用"""
    from app.models.models import AutomationSetting
    db = SessionLocal()
    try:
        r = db.query(AutomationSetting).filter(AutomationSetting.key == key).first()
        return r.value if r else default
    finally:
        db.close()


def _state_set(key: str, value: str):
    from app.models.models import AutomationSetting
    db = SessionLocal()
    try:
        r = db.query(AutomationSetting).filter(AutomationSetting.key == key).first()
        if r:
            r.value = str(value)
        else:
            db.add(AutomationSetting(key=key, value=str(value)))
        db.commit()
    finally:
        db.close()


def _state_set_timestamp(key: str):
    _state_set(key, datetime.utcnow().isoformat())


# ============== chunk expand-training (cursor付き) ==============
def expand_training_chunked(market: str = "JP", chunk_size: int = 50,
                             max_chunks_per_run: int = 2,
                             priority_mode: str = "all_eligible") -> Dict:
    """cursor付きchunk実行: automation_stateから offset を読み, max_chunks_per_run回処理"""
    offset_key = f"surge20_{market.lower()}_expand_offset"
    try:
        current_offset = int(_state_get(offset_key, "0"))
    except ValueError:
        current_offset = 0

    syms = universe_db.list_eligible_yahoo_symbols(
        markets=[market], max_count=0, include_adr=True
    )
    total_universe = len(syms)
    if total_universe == 0:
        return {"status": "no_universe"}

    end_offset = min(current_offset + chunk_size * max_chunks_per_run, total_universe)
    target_syms = syms[current_offset:end_offset]

    total_events = 0; total_features = 0; total_negatives = 0
    for chunk_start in range(0, len(target_syms), chunk_size):
        chunk = target_syms[chunk_start: chunk_start + chunk_size]
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
        try:
            fres = extract_pre_features_for_recent_events(limit=200)
            total_features += fres.get("features_created", 0)
        except Exception as e:
            print(f"extract failed: {e}")
        for s in chunk:
            try:
                total_negatives += generate_negative_cases_for_symbol(
                    s["yahoo_symbol"], s.get("market") or market, max_cases=15
                )
            except Exception:
                pass

    # cursor 更新
    next_offset = end_offset if end_offset < total_universe else 0  # 一巡したら戻す
    _state_set(offset_key, str(next_offset))
    _state_set_timestamp(f"surge20_{market.lower()}_last_expand_at")

    return {
        "status": "ok",
        "market": market,
        "previous_offset": current_offset,
        "next_offset": next_offset,
        "processed_symbols": len(target_syms),
        "total_universe": total_universe,
        "events_saved": total_events,
        "features_created": total_features,
        "negatives_created": total_negatives,
        "cycle_completed": next_offset == 0,
    }


# ============== 候補をDB保存 + auto-save ==============
def build_and_save_candidates(market: str = "JP", max_symbols: int = 200,
                               min_similarity: float = 0.4, start_offset: Optional[int] = None) -> Dict:
    """候補を生成して surge_20_candidates に保存。

    start_offset=None の場合は automation_state のカーソルから開始し、
    実行後にカーソルを max_symbols 分進める (universe全体を日次で巡回)。
    """
    from app.models.models import Surge20Candidate

    offset_key = f"surge20_{market.lower()}_candidate_offset"
    use_cursor = start_offset is None
    if use_cursor:
        try:
            start_offset = int(_state_get(offset_key, "0"))
        except Exception:
            start_offset = 0

    r = build_candidates(market=market, max_symbols=max_symbols,
                         min_similarity=min_similarity, start_offset=start_offset or 0)
    if r.get("status") != "ok":
        return r

    # rolling cursor を進める (一巡したら0に戻す)
    total_eligible = r.get("total_eligible", 0)
    next_offset = (start_offset or 0) + max_symbols
    if not total_eligible or next_offset >= total_eligible:
        next_offset = 0
    if use_cursor:
        _state_set(offset_key, str(next_offset))

    today = date.today().isoformat()
    saved = 0
    updated = 0
    for c in r.get("candidates_top50", []):
        db = SessionLocal()
        try:
            existing = (db.query(Surge20Candidate)
                        .filter(Surge20Candidate.symbol == c["symbol"])
                        .filter(Surge20Candidate.candidate_date == today)
                        .first())
            score = (c.get("positive_similarity") or 0) * 100
            cp = c.get("current_price")
            # entry/stop/target の簡易算出 (現値ベース)
            entry_low = round(cp * 0.97, 2) if cp else None
            entry_high = round(cp * 1.01, 2) if cp else None
            stop = round(cp * 0.92, 2) if cp else None
            tp1 = round(cp * 1.10, 2) if cp else None
            tp2 = round(cp * 1.20, 2) if cp else None
            payload = {
                "symbol": c["symbol"],
                "market": c.get("market") or market,
                "name": c.get("name"),
                "candidate_date": today,
                "final_surge_20_score": score,
                "candidate_label": c.get("candidate_label"),
                "prediction_horizon": "within_20d",
                "current_price": cp,
                "entry_zone_low": entry_low,
                "entry_zone_high": entry_high,
                "stop_loss": stop,
                "first_target": tp1,
                "second_target": tp2,
                "support_distance": c.get("support_distance"),
                "resistance_upside": c.get("resistance_upside"),
                "positive_similarity": c.get("positive_similarity"),
                "negative_similarity": c.get("negative_similarity"),
                "similarity_gap": c.get("similarity_diff"),
                "overextension_score": c.get("overextension_score"),
                "reason_summary": f"pos={c.get('positive_similarity'):.2f} neg={c.get('negative_similarity'):.2f}",
                "risk_summary": (c.get("candidate_label") if c.get("candidate_label") in ("上がり切り警戒", "後追い危険", "negative類似高め") else None),
            }
            if existing:
                for k, v in payload.items():
                    if k not in ("symbol", "candidate_date"):
                        setattr(existing, k, v)
                updated += 1
            else:
                db.add(Surge20Candidate(**payload))
                saved += 1
            db.commit()
        except Exception as e:
            db.rollback()
            print(f"save candidate {c.get('symbol')} failed: {e}")
        finally:
            db.close()

    _state_set_timestamp("surge20_last_candidate_build_at")
    return {
        "status": "ok",
        "market": market,
        "candidate_date": today,
        "candidates_count": r.get("candidates_count"),
        "saved": saved,
        "updated": updated,
        "by_label": r.get("by_label"),
        "universe_scanned": r.get("universe_scanned"),
        "start_offset": start_offset,
        "next_offset": next_offset,
        "total_eligible": total_eligible,
        "cycle_completed": next_offset == 0,
    }


MAIN_AUTO_SAVE_LABELS = {
    "本命20%到達候補", "20日以内20%候補", "1か月以内20%候補",
}
WATCH_AUTO_SAVE_LABELS = {
    "出来高初動候補", "二段目候補", "押し目再上昇候補",
}
REJECTED_WATCH_LABEL = "見送り"
LATE_CHASE_WATCH_LABELS = {"上がり切り警戒", "後追い危険"}
NEGATIVE_SIM_WATCH_LABEL = "negative類似高め"

AUTO_SAVE_MAX_MAIN_PER_DAY = 20
AUTO_SAVE_MAX_WATCH_PER_DAY = 50


def _classify_save_type(c) -> Optional[tuple]:
    """候補を4種類のprediction_typeに分類し、(type, auto_trade_candidate, watch_only) を返す
    本命: surge_20_prediction
    watch: surge_20_watch_prediction
    rejected: surge_20_rejected_watch
    late_chase: surge_20_late_chase_watch
    None: 保存しない (条件不足など)
    """
    label = c.candidate_label or ""
    score = c.final_surge_20_score or 0
    neg_sim = c.negative_similarity or 0
    overext = c.overextension_score or 0
    upside = c.resistance_upside or 0

    # 本命条件 (全て満たす場合のみ main)
    main_ok = (
        score >= 70 and
        label in MAIN_AUTO_SAVE_LABELS and
        neg_sim < 0.65 and
        overext < 70 and
        upside >= 10 and
        c.current_price and c.current_price > 0
    )
    if main_ok:
        return ("surge_20_prediction", True, False)

    # late_chase系
    if label in LATE_CHASE_WATCH_LABELS:
        return ("surge_20_late_chase_watch", False, True)

    # 見送り
    if label == REJECTED_WATCH_LABEL:
        return ("surge_20_rejected_watch", False, True)

    # watch系: 出来高初動/二段目/押し目再上昇/negative類似高め/本命系だが条件未達
    if label in WATCH_AUTO_SAVE_LABELS or label == NEGATIVE_SIM_WATCH_LABEL:
        return ("surge_20_watch_prediction", False, True)

    # 本命系の条件付き (score>=70だが他の条件未達)
    if label in MAIN_AUTO_SAVE_LABELS and score >= 70:
        return ("surge_20_watch_prediction", False, True)

    return None


def auto_save_top_candidates(market: str = "JP", limit: int = 20,
                              min_score: float = 70.0) -> Dict:
    """surge_20_candidates から4種類のprediction_typeで自動保存
    - main: 本命20件まで
    - watch / rejected / late_chase: 合計50件まで
    """
    from app.models.models import Surge20Candidate, PredictionLog
    today = date.today().isoformat()

    db = SessionLocal()
    try:
        cands = (db.query(Surge20Candidate)
                 .filter(Surge20Candidate.market == market)
                 .filter(Surge20Candidate.candidate_date == today)
                 .filter(Surge20Candidate.auto_saved_as_prediction == False)
                 .order_by(Surge20Candidate.final_surge_20_score.desc())
                 .all())
    finally:
        db.close()

    main_saved = 0
    watch_saved = 0
    rejected_watch_saved = 0
    late_chase_watch_saved = 0
    skipped_duplicate = 0
    skipped_data_quality = 0
    skipped_error = 0

    for c in cands:
        # 上限チェック
        if (main_saved >= AUTO_SAVE_MAX_MAIN_PER_DAY and
            (watch_saved + rejected_watch_saved + late_chase_watch_saved) >= AUTO_SAVE_MAX_WATCH_PER_DAY):
            break

        # 必須データ
        if not c.current_price or c.current_price <= 0:
            skipped_data_quality += 1
            continue

        classification = _classify_save_type(c)
        if not classification:
            skipped_data_quality += 1
            continue

        pred_type, auto_trade, watch_only = classification

        # 上限グループ別チェック
        if pred_type == "surge_20_prediction" and main_saved >= AUTO_SAVE_MAX_MAIN_PER_DAY:
            continue
        if pred_type != "surge_20_prediction":
            total_watch = watch_saved + rejected_watch_saved + late_chase_watch_saved
            if total_watch >= AUTO_SAVE_MAX_WATCH_PER_DAY:
                continue

        # 同一symbol + prediction_date + prediction_type の重複チェック
        check_db = SessionLocal()
        try:
            existing = (check_db.query(PredictionLog)
                        .filter(PredictionLog.symbol == c.symbol)
                        .filter(PredictionLog.prediction_date == today)
                        .filter(PredictionLog.prediction_type == pred_type)
                        .first())
            if existing:
                skipped_duplicate += 1
                continue
        finally:
            check_db.close()

        # 本命だけ、直近7日open重複チェック
        if pred_type == "surge_20_prediction":
            check2 = SessionLocal()
            try:
                from datetime import timedelta as td
                seven_days_ago = (date.today() - td(days=7)).isoformat()
                recent = (check2.query(PredictionLog)
                          .filter(PredictionLog.symbol == c.symbol)
                          .filter(PredictionLog.prediction_type == "surge_20_prediction")
                          .filter(PredictionLog.status == "open")
                          .filter(PredictionLog.prediction_date >= seven_days_ago)
                          .first())
                if recent:
                    skipped_duplicate += 1
                    continue
            finally:
                check2.close()

        # 保存
        save_db = SessionLocal()
        try:
            log = PredictionLog(
                symbol=c.symbol, yahoo_symbol=c.symbol,
                name=c.name, market=c.market,
                prediction_date=today,
                current_price_at_prediction=c.current_price,
                jpy_price_at_prediction=c.current_price,
                prediction_label=c.candidate_label,
                final_prediction_score=c.final_surge_20_score,
                prediction_type=pred_type,
                prediction_horizon="within_20d",
                target_return=20.0,
                auto_trade_candidate=auto_trade,
                watch_only=watch_only,
                entry_type="surge_20_auto" if not watch_only else "watch_only",
                entry_zone_a_low=c.entry_zone_low,
                entry_zone_a_high=c.entry_zone_high,
                stop_loss_price=c.stop_loss,
                take_profit_1=c.first_target,
                take_profit_2=c.second_target,
                positive_case_similarity=c.positive_similarity,
                negative_case_similarity=c.negative_similarity,
                reason_summary=c.reason_summary,
                avoid_condition=c.risk_summary,
                status="open",
            )
            save_db.add(log); save_db.flush()
            log_id = log.id

            # main の場合のみ candidate.auto_saved_as_prediction=True
            if pred_type == "surge_20_prediction":
                cand_db_row = save_db.query(Surge20Candidate).filter(Surge20Candidate.id == c.id).first()
                if cand_db_row:
                    cand_db_row.auto_saved_as_prediction = True
                    cand_db_row.prediction_log_id = log_id
            save_db.commit()

            if pred_type == "surge_20_prediction":
                main_saved += 1
            elif pred_type == "surge_20_watch_prediction":
                watch_saved += 1
            elif pred_type == "surge_20_rejected_watch":
                rejected_watch_saved += 1
            elif pred_type == "surge_20_late_chase_watch":
                late_chase_watch_saved += 1
        except Exception as e:
            save_db.rollback()
            skipped_error += 1
            print(f"auto-save {c.symbol} ({pred_type}) failed: {e}")
        finally:
            save_db.close()

    _state_set_timestamp(f"surge20_{market.lower()}_last_auto_save_at")
    return {
        "status": "ok", "market": market,
        "candidates_checked": len(cands),
        "main_saved": main_saved,
        "watch_saved": watch_saved,
        "rejected_watch_saved": rejected_watch_saved,
        "late_chase_watch_saved": late_chase_watch_saved,
        "total_saved": main_saved + watch_saved + rejected_watch_saved + late_chase_watch_saved,
        "skipped_duplicate": skipped_duplicate,
        "skipped_data_quality": skipped_data_quality,
        "skipped_error": skipped_error,
        # 後方互換
        "saved": main_saved,
        "skipped": skipped_duplicate + skipped_data_quality + skipped_error,
    }


# ============== Auto Orchestrator ==============
def run_auto_orchestrator(market: str = "JP", phase: str = "full_light",
                          chunk_size: int = 20, max_seconds: int = 90) -> Dict:
    """surge-20 をphase分割で実行。Render Free対策で各stepは小さく + 同時実行lock。

    phase:
      data_quality / cleanup / expand_one_chunk / candidate_build /
      auto_save / review_predictions / save_reviews_as_training /
      full_light / all(後方互換)
    """
    # 軽い phase は lock 不要 (data_quality / auto_save は DBのみ)
    LIGHT_PHASES = {"data_quality", "auto_save", "save_reviews_as_training"}
    needs_lock = phase not in LIGHT_PHASES

    if needs_lock and not _acquire_heavy(f"orchestrator/{market}/{phase}"):
        return {"status": "busy", "message": f"別の重い処理が実行中: {_heavy_running['task']}"}

    import time as _time
    t_start = _time.time()
    results = {}
    partial = False
    try:
        def _elapsed():
            return _time.time() - t_start

        # ---- data_quality (軽) ----
        if phase in ("data_quality", "full_light", "all"):
            try:
                results["data_quality"] = get_data_quality()
            except Exception as e:
                results["data_quality_error"] = str(e)

        # ---- cleanup orphan (軽) ----
        if phase in ("cleanup", "full_light", "all"):
            try:
                dq = results.get("data_quality") or {}
                if dq.get("orphan_pre_features", 0) > 0 or phase == "cleanup":
                    results["orphan_cleanup"] = cleanup_orphan_pre_features()
            except Exception as e:
                results["orphan_cleanup_error"] = str(e)

        # ---- expand one chunk (重) ----
        if phase in ("expand_one_chunk", "expand", "full_light", "all"):
            if _elapsed() < max_seconds:
                try:
                    results["expand_training"] = expand_training_chunked(
                        market=market, chunk_size=chunk_size, max_chunks_per_run=1,
                        priority_mode="all_eligible",
                    )
                except Exception as e:
                    results["expand_training_error"] = str(e)
            else:
                partial = True

        # ---- candidate_build (重) ----
        if phase in ("candidate_build", "candidates", "full_light", "all"):
            if _elapsed() < max_seconds:
                try:
                    results["candidate_build"] = build_and_save_candidates(
                        market=market, max_symbols=50, min_similarity=0.4,
                    )
                except Exception as e:
                    results["candidate_error"] = str(e)
            else:
                partial = True

        # ---- auto_save (軽) ----
        if phase in ("auto_save", "candidate_build", "candidates", "full_light", "all"):
            try:
                results["auto_save"] = auto_save_top_candidates(
                    market=market, limit=20, min_score=70.0,
                )
            except Exception as e:
                results["auto_save_error"] = str(e)

        # ---- review (軽: DBのみ) ----
        if phase in ("review_predictions", "review", "all"):
            try:
                results["review"] = review_surge_20_predictions(limit=50)
            except Exception as e:
                results["review_error"] = str(e)

        # ---- save reviews as training (軽) ----
        if phase in ("save_reviews_as_training", "review", "all"):
            try:
                results["training_save"] = save_surge_20_reviews_as_training()
            except Exception as e:
                results["training_save_error"] = str(e)

        _state_set_timestamp("surge20_last_orchestrator_at")
        status = "partial_complete" if partial else "completed"
        return {"status": status, "market": market, "phase": phase,
                "duration_sec": round(_elapsed(), 2), "results": results}
    finally:
        if needs_lock:
            _release_heavy()


# ============== サマリ追加用 helper ==============
def get_orchestrator_state() -> Dict:
    """automation_state の cursor / timestamp 群を返す"""
    keys = [
        "surge20_jp_expand_offset", "surge20_us_expand_offset",
        "surge20_jp_last_expand_at", "surge20_us_last_expand_at",
        "surge20_last_candidate_build_at",
        "surge20_jp_last_auto_save_at", "surge20_us_last_auto_save_at",
        "surge20_last_orchestrator_at",
    ]
    return {k: _state_get(k, "") for k in keys}


# ============== surge_20_prediction 保存 / 検証 / 教師化 ==============
def save_candidate_as_prediction(body: Dict) -> Dict:
    """候補を prediction_logs に surge_20_prediction として保存"""
    from app.models.models import PredictionLog
    from datetime import date

    db = SessionLocal()
    try:
        sym = body.get("symbol")
        market = body.get("market") or "JP"
        if not sym:
            return {"status": "failed", "error": "symbol required"}

        # 同日重複防止
        today_str = date.today().isoformat()
        existing = (db.query(PredictionLog)
                    .filter(PredictionLog.symbol == sym)
                    .filter(PredictionLog.prediction_date == today_str)
                    .filter(PredictionLog.prediction_type == "surge_20_prediction")
                    .first())
        if existing:
            return {"status": "already_exists", "log_id": existing.id}

        row = PredictionLog(
            symbol=sym, yahoo_symbol=sym,
            name=body.get("name"),
            market=market,
            prediction_date=today_str,
            current_price_at_prediction=body.get("current_price"),
            jpy_price_at_prediction=body.get("current_price"),
            prediction_label=body.get("candidate_label") or "surge_20_candidate",
            final_prediction_score=body.get("final_surge_20_score") or 0,
            prediction_type="surge_20_prediction",
            prediction_horizon=body.get("prediction_horizon") or "within_20d",
            target_return=body.get("target_return") or 20.0,
            entry_type="surge_20",
            entry_zone_a_low=body.get("entry_zone_low"),
            entry_zone_a_high=body.get("entry_zone_high"),
            stop_loss_price=body.get("stop_loss"),
            take_profit_1=body.get("first_target"),
            take_profit_2=body.get("second_target"),
            positive_case_similarity=body.get("positive_similarity"),
            negative_case_similarity=body.get("negative_similarity"),
            reason_summary=body.get("reason_summary"),
            avoid_condition=body.get("risk_summary"),
            matched_past_cases=body.get("similar_past_20_events"),
            status="open",
        )
        db.add(row); db.commit()
        return {"status": "ok", "log_id": row.id, "prediction_type": "surge_20_prediction"}
    finally:
        db.close()


def _classify_surge_20_result(predicted_at: str, max_gain: float, max_drawdown: float,
                              hit_20: bool, stop_loss_hit: bool, elapsed_days: int,
                              prediction_type: str = "surge_20_prediction") -> tuple:
    """surge_20系の結果判定。prediction_type別に解釈を変える
    Returns (result_label, failure_reason)
    """
    if elapsed_days < 5:
        return "still_open", None
    if elapsed_days < 20 and not hit_20 and not stop_loss_hit:
        return "insufficient_days", None

    # 本命: 成功 = +20% / 失敗 = +10%未満
    if prediction_type == "surge_20_prediction":
        if stop_loss_hit and not hit_20:
            return "stopped_out", "stopped_out"
        if hit_20:
            if elapsed_days <= 5:
                return "high_quality_success_20_within_5d", None
            if elapsed_days <= 10:
                return "success_20_within_10d", None
            return "success_20_within_20d", None
        if max_gain >= 15:
            return "conditional_success_15", None
        if max_gain >= 10:
            return "short_reaction_success_10", None
        return "failed_under_10", "failed_under_10"

    # 見送り: +20%未達 = 見送り正解 / +20%到達 = 見送り失敗
    if prediction_type == "surge_20_rejected_watch":
        if hit_20:
            return "rejected_watch_missed_positive", "missed_positive"
        if max_gain < 10:
            return "rejected_watch_correct", None
        if max_gain < 20:
            return "rejected_watch_partial", None
        return "rejected_watch_correct", None

    # 後追い警戒: 下落・横ばい = 警戒正解 / +20%到達 = 後追い警戒ミス(=二段目)
    if prediction_type == "surge_20_late_chase_watch":
        if hit_20:
            return "late_chase_missed_continuation", "missed_continuation_surge"
        if max_drawdown <= -10 or max_gain < 5:
            return "late_chase_correct", None
        if max_gain < 10:
            return "late_chase_correct", None
        return "late_chase_partial", None

    # 条件付きwatch: +20%到達 = 条件付き成功 / +10〜20% = 短期反応 / +10%未満 = 失敗
    if prediction_type == "surge_20_watch_prediction":
        if hit_20:
            return "watch_conditional_success", None
        if max_gain >= 15:
            return "watch_short_reaction_15", None
        if max_gain >= 10:
            return "watch_short_reaction_10", None
        return "watch_failed_under_10", "watch_failed_under_10"

    # fallback
    if hit_20:
        return "success_20_within_20d", None
    return "failed_under_10", "failed_under_10"


SURGE_20_PREDICTION_TYPES = (
    "surge_20_prediction", "surge_20_watch_prediction",
    "surge_20_rejected_watch", "surge_20_late_chase_watch",
)


def review_surge_20_predictions(limit: int = 200) -> Dict:
    """surge_20系全prediction_type の T+5/T+10/T+20 検証 + result_label保存"""
    from app.models.models import PredictionLog, PredictionOutcome, PredictionReview
    from datetime import date, datetime as dt

    db = SessionLocal()
    try:
        logs = (db.query(PredictionLog)
                .filter(PredictionLog.prediction_type.in_(SURGE_20_PREDICTION_TYPES))
                .limit(limit).all())
        log_ids = [l.id for l in logs]
    finally:
        db.close()

    reviewed_count = 0
    still_open_count = 0
    insufficient_count = 0
    success_count = 0
    failed_count = 0

    for lid in log_ids:
        db = SessionLocal()
        try:
            log = db.query(PredictionLog).filter(PredictionLog.id == lid).first()
            if not log:
                continue
            df = _list_history(log.symbol)
            if df is None or len(df) < 5:
                continue
            df = df.sort_values("date").reset_index(drop=True)
            # T0 = prediction_date 以降のデータ
            future = df[df["date"].astype(str) > log.prediction_date]
            elapsed = len(future)
            if elapsed == 0:
                still_open_count += 1
                continue

            entry_price = log.current_price_at_prediction or 0
            if entry_price <= 0:
                continue

            highs = future["high"].astype(float).values
            lows = future["low"].astype(float).values
            max_hi = float(max([float(h) for h in highs if not math.isnan(float(h))]))
            min_lo = float(min([float(l) for l in lows if not math.isnan(float(l))]))
            max_gain = (max_hi - entry_price) / entry_price * 100
            max_dd = (min_lo - entry_price) / entry_price * 100
            hit_20 = max_gain >= 20.0
            stop_hit = bool(log.stop_loss_price and min_lo <= log.stop_loss_price)

            result_label, failure_reason = _classify_surge_20_result(
                log.prediction_date, max_gain, max_dd, hit_20, stop_hit, elapsed,
                prediction_type=log.prediction_type or "surge_20_prediction",
            )

            # prediction_type別の教師データ化フラグ
            pos_labels = (
                "high_quality_success_20_within_5d",
                "success_20_within_10d",
                "success_20_within_20d",
                "conditional_success_15",
                # 後追い警戒ミス = 二段目positive
                "late_chase_missed_continuation",
                # 見送りミス = positive取り逃し
                "rejected_watch_missed_positive",
                # 条件付きwatch成功
                "watch_conditional_success",
            )
            neg_labels = (
                "failed_under_10",
                "stopped_out",
                "late_chase_only",
                "watch_failed_under_10",
                # 後追い警戒正解 = late_chase_negative
                "late_chase_correct",
                # 見送り正解 = negative回避ロジック成功
                "rejected_watch_correct",
            )
            should_pos = result_label in pos_labels
            should_neg = result_label in neg_labels

            # PredictionReview に保存
            db.query(PredictionReview).filter(PredictionReview.prediction_log_id == lid).delete()
            rev = PredictionReview(
                prediction_log_id=lid,
                symbol=log.symbol,
                prediction_date=log.prediction_date,
                review_date=date.today().isoformat(),
                success_label=result_label,
                success_score=(95.0 if hit_20 else (60.0 if max_gain >= 15 else (30.0 if max_gain >= 10 else 10.0))),
                max_gain=round(max_gain, 3),
                max_drawdown=round(max_dd, 3),
                hit_20_percent=hit_20,
                stop_loss_hit=stop_hit,
                entry_plan_worked=hit_20 or max_gain >= 15,
                failed_reason_category=failure_reason,
                ai_review_comment=f"{log.prediction_type} review: elapsed={elapsed}d max_gain={max_gain:.2f}% max_dd={max_dd:.2f}% result={result_label}",
                should_save_as_positive_training=should_pos,
                should_save_as_negative_training=should_neg,
                saved_as_training=False,
            )
            db.add(rev)
            if result_label not in ("still_open", "insufficient_days"):
                log.status = "reviewed"
            db.commit()

            if result_label == "still_open":
                still_open_count += 1
            elif result_label == "insufficient_days":
                insufficient_count += 1
            elif "success" in result_label:
                success_count += 1
            else:
                failed_count += 1
            reviewed_count += 1
        except Exception as e:
            db.rollback()
            print(f"review surge_20 {lid} failed: {e}")
        finally:
            db.close()

    return {
        "status": "ok",
        "logs_processed": len(log_ids),
        "reviewed": reviewed_count,
        "still_open": still_open_count,
        "insufficient_days": insufficient_count,
        "success": success_count,
        "failed": failed_count,
    }


def save_surge_20_reviews_as_training() -> Dict:
    """review結果をsurge_20_pre_features (positive) または surge_20_negative_cases (negative)に保存"""
    from app.models.models import PredictionLog, PredictionReview

    db = SessionLocal()
    try:
        reviews = (db.query(PredictionReview)
                   .filter(PredictionReview.saved_as_training == False)
                   .filter((PredictionReview.should_save_as_positive_training == True) |
                           (PredictionReview.should_save_as_negative_training == True))
                   .all())
        pairs = [(r, db.query(PredictionLog).filter(PredictionLog.id == r.prediction_log_id).first())
                 for r in reviews]
    finally:
        db.close()

    positive_saved = 0
    negative_saved = 0
    for rev, log in pairs:
        if not log or log.prediction_type != "surge_20_prediction":
            continue
        try:
            if rev.should_save_as_positive_training:
                # positive: surge_20_events + pre_features に追加
                # 簡易: もう既存eventがある場合スキップ
                event_db = SessionLocal()
                try:
                    existing = (event_db.query(Surge20Event)
                                .filter(Surge20Event.symbol == log.symbol)
                                .filter(Surge20Event.event_start_date == log.prediction_date)
                                .first())
                    if not existing:
                        event_db.add(Surge20Event(
                            symbol=log.symbol, yahoo_symbol=log.symbol,
                            name=log.name, market=log.market,
                            event_type="hit_20_within_20d",
                            event_start_date=log.prediction_date,
                            start_price=log.current_price_at_prediction,
                            max_gain_percent=rev.max_gain,
                            source_type="prediction_review",
                            material_confirmed=log.material_confirmed,
                            catalyst_category=log.catalyst_category,
                        ))
                        event_db.commit()
                        positive_saved += 1
                finally:
                    event_db.close()
            elif rev.should_save_as_negative_training:
                neg_db = SessionLocal()
                try:
                    existing = (neg_db.query(Surge20NegativeCase)
                                .filter(Surge20NegativeCase.symbol == log.symbol)
                                .filter(Surge20NegativeCase.asof_date == log.prediction_date)
                                .first())
                    if not existing:
                        reason = rev.failed_reason_category or "false_positive_similarity"
                        neg_db.add(Surge20NegativeCase(
                            symbol=log.symbol, market=log.market,
                            asof_date=log.prediction_date,
                            reason=reason,
                            max_gain_next_20d=rev.max_gain,
                            hit_20_next_20d=rev.hit_20_percent,
                            failure_reason=rev.ai_review_comment,
                        ))
                        neg_db.commit()
                        negative_saved += 1
                finally:
                    neg_db.close()

            # mark saved
            mark_db = SessionLocal()
            try:
                r = mark_db.query(PredictionReview).filter(PredictionReview.id == rev.id).first()
                if r:
                    r.saved_as_training = True
                    mark_db.commit()
            finally:
                mark_db.close()
        except Exception as e:
            print(f"save_surge_20_review {rev.id} failed: {e}")

    return {"status": "ok", "positive_saved": positive_saved, "negative_saved": negative_saved}


def get_surge_20_prediction_performance() -> Dict:
    """surge_20系 全prediction_type の検証結果集計"""
    from app.models.models import PredictionLog, PredictionReview

    db = SessionLocal()
    try:
        logs = (db.query(PredictionLog)
                .filter(PredictionLog.prediction_type.in_(SURGE_20_PREDICTION_TYPES)).all())
        log_ids = [l.id for l in logs]
        reviews = (db.query(PredictionReview)
                   .filter(PredictionReview.prediction_log_id.in_(log_ids)).all()) if log_ids else []
        rev_by_log = {r.prediction_log_id: r for r in reviews}

        # prediction_type 別 + result_label別
        by_type_total: Dict = {}
        by_type_label: Dict = {}
        saved_training = 0
        for log in logs:
            pt = log.prediction_type or "unknown"
            by_type_total[pt] = by_type_total.get(pt, 0) + 1
            rev = rev_by_log.get(log.id)
            label = (rev.success_label if rev else None) or "未検証"
            by_type_label.setdefault(pt, {})
            by_type_label[pt][label] = by_type_label[pt].get(label, 0) + 1
            if rev and rev.saved_as_training:
                saved_training += 1

        return {
            "total_predictions": len(logs),
            "by_prediction_type": by_type_total,
            "by_type_and_label": by_type_label,
            "saved_as_training": saved_training,
            # 後方互換 (本命のみ)
            "total_surge_20_predictions": by_type_total.get("surge_20_prediction", 0),
            "by_result_label": by_type_label.get("surge_20_prediction", {}),
        }
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


# ============== 20%到達候補生成 (orphan除外 + negative_similarity) ==============
def _classify_candidate(positive_sim: float, negative_sim: float, current: Dict) -> str:
    """候補分類"""
    overext = current.get("t1_overextension_score") or 0
    pc20 = current.get("t1_price_change_20d") or 0
    upside = current.get("t1_resistance_upside") or 0
    diff = positive_sim - negative_sim

    if overext >= 70 or pc20 >= 80:
        return "上がり切り警戒"
    if overext >= 60 or pc20 >= 60:
        return "後追い危険"
    if negative_sim >= positive_sim + 0.05:
        return "negative類似高め"
    if upside < 15:
        return "見送り"
    if positive_sim >= 0.7 and diff >= 0.1:
        return "本命20%到達候補"
    if positive_sim >= 0.6 and diff >= 0.05:
        return "20日以内20%候補"
    if positive_sim >= 0.5:
        if pc20 >= 20:
            return "二段目候補"
        return "1か月以内20%候補"
    if positive_sim >= 0.4:
        return "出来高初動候補"
    return "見送り"


def build_candidates(market: str = "JP", max_symbols: int = 200,
                     min_similarity: float = 0.4, start_offset: int = 0) -> Dict:
    """過去 surge_20 イベント に紐づく valid pre_features と類似度マッチで候補生成。
    削除済み event の orphan features は除外。T0 は学習特徴量に含めない。
    negative_similarity も同時計算し、候補分類する。
    start_offset: universe走査の開始位置 (rolling cursor 用)。
    """
    from app.services.predictor import _numeric_distance, compute_current_features, compute_dynamic_weights
    from app.models.models import TrainingFeatureVector as TFV

    # データ駆動の動的重み (positive/negative の平均差から判別力を計算)
    dyn_weights = compute_dynamic_weights()

    db = SessionLocal()
    try:
        # 有効 event_id + 品質係数 (max_gain_percent / days_to_hit_20)
        # 高い品質 (大幅急騰・短期到達) ほど類似度計算で重みが上がる
        event_rows = db.query(
            Surge20Event.id,
            Surge20Event.max_gain_percent,
            Surge20Event.days_to_hit_20,
        ).all()
        event_ids = {e[0] for e in event_rows}
        event_quality: Dict[int, float] = {}
        for eid, gain, days in event_rows:
            g = float(gain) if gain is not None else 20.0
            d = float(days) if days else 20.0
            # gain 20% を基準に 0.5〜2.0、days 短いほど高い、合計を 0.3〜2.0 にclip
            q = min(2.0, max(0.5, g / 25.0)) * (20.0 / max(d, 5.0)) * 0.7
            event_quality[eid] = max(0.3, min(2.0, q))

        # T0を除いた valid pre_features
        pres = (db.query(Surge20PreFeature)
                .filter(Surge20PreFeature.relative_day.in_(["T-20", "T-10", "T-5", "T-3", "T-1"]))
                .all())
        valid_features = [p for p in pres if p.surge_event_id in event_ids]
        orphan_count = len(pres) - len(valid_features)

        positive_library = [{
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
            "quality": event_quality.get(p.surge_event_id, 1.0),
        } for p in valid_features]

        # negative library: TrainingFeatureVector の失敗/非急騰ケースを使う
        # (旧実装は Surge20NegativeCase の symbol/reason だけでハードコードrule評価していた)
        neg_case_types = [
            "negative_non_surge", "failed_overextended",
            "failed_weak_material", "failed_material_exhaustion", "failed_bad_news",
        ]
        neg_tfvs = (db.query(TFV)
                    .filter(TFV.case_type.in_(neg_case_types))
                    .limit(3000).all())
        negative_library = [{
            "case_id": t.id,
            "symbol": t.symbol,
            "case_type": t.case_type,
            "t1_volume_ratio_20d": t.volume_ratio_20d,
            "t1_price_change_5d": t.price_change_5d,
            "t1_price_change_20d": t.price_change_20d,
            "t1_ma25_deviation": t.ma25_deviation,
            "t1_resistance_upside": t.resistance_upside,
            "t1_support_distance": t.support_distance,
            "t1_overextension_score": t.overextension_score,
        } for t in neg_tfvs]
    finally:
        db.close()

    if not positive_library:
        return {"status": "no_library", "message": "valid pre_features がありません",
                "orphan_pre_features": orphan_count}

    total_eligible = universe_db.count_eligible_yahoo_symbols(markets=[market], include_adr=True)
    syms = universe_db.list_eligible_yahoo_symbols(
        markets=[market], max_count=max_symbols, include_adr=True, offset=start_offset,
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

        # positive 類似: relative_day で層化マッチング + 過去急騰の品質で重み付け
        # T-1 (直前のセットアップ) を最重視し、T-3/T-5/T-10/T-20 ほど影響を下げる。
        # 各 relative_day 内では quality (max_gain/days_to_hit由来) で重み付き top3 平均。
        RD_WEIGHT = {"T-1": 3.0, "T-3": 2.0, "T-5": 1.5, "T-10": 1.0, "T-20": 0.5}
        rd_buckets: Dict[str, list] = {rd: [] for rd in RD_WEIGHT}
        for c in positive_library:
            rd = c.get("relative_day")
            if rd in rd_buckets:
                rd_buckets[rd].append(c)
        rd_sims: Dict[str, float] = {}
        for rd, entries in rd_buckets.items():
            if not entries:
                continue
            scored = []
            for c in entries:
                dist = _numeric_distance(current, c, weights=dyn_weights)
                sim = max(0.0, 1.0 - dist)
                scored.append((sim, c.get("quality", 1.0)))
            scored.sort(reverse=True, key=lambda x: x[0])
            top = scored[:5]
            wsum = sum(s * q for s, q in top)
            qsum = sum(q for _, q in top)
            rd_sims[rd] = (wsum / qsum) if qsum > 0 else 0.0
        if rd_sims:
            wnum = sum(RD_WEIGHT[rd] * s for rd, s in rd_sims.items())
            wden = sum(RD_WEIGHT[rd] for rd in rd_sims)
            positive_sim = wnum / wden if wden > 0 else 0.0
        else:
            positive_sim = 0.0

        # negative 類似 (TrainingFeatureVector の失敗ケース群との同じ距離指標)
        # 旧 hard-coded rule を廃止し、本物のデータ駆動マッチへ
        if negative_library:
            neg_scored = []
            for n in negative_library:
                dist = _numeric_distance(current, n, weights=dyn_weights)
                neg_scored.append(max(0.0, 1.0 - dist))
            neg_scored.sort(reverse=True)
            negative_sim = sum(neg_scored[:5]) / max(1, len(neg_scored[:5]))
        else:
            negative_sim = 0.0
        # 過熱・低出来高は学習データに表れにくいので、補強として小さくブースト
        overext = current.get("t1_overextension_score") or 0
        upside = current.get("t1_resistance_upside") or 0
        if overext >= 70:
            negative_sim = min(1.0, negative_sim + 0.15)
        if upside < 5:
            negative_sim = min(1.0, negative_sim + 0.10)

        if positive_sim < min_similarity:
            continue

        candidate_label = _classify_candidate(positive_sim, negative_sim, current)

        candidates.append({
            "symbol": sym,
            "name": s.get("name"),
            "market": market_s,
            "current_price": current.get("t1_close") or current.get("close"),
            "positive_similarity": round(positive_sim, 4),
            "negative_similarity": round(negative_sim, 4),
            "similarity_diff": round(positive_sim - negative_sim, 4),
            "avg_similarity_top5": round(positive_sim, 4),  # 後方互換
            "candidate_label": candidate_label,
            "resistance_upside": current.get("t1_resistance_upside"),
            "ma25_deviation": current.get("t1_ma25_deviation"),
            "overextension_score": current.get("t1_overextension_score"),
            "support_distance": current.get("t1_support_distance"),
            "price_change_5d": current.get("t1_price_change_5d"),
            "price_change_20d": current.get("t1_price_change_20d"),
        })

    candidates.sort(key=lambda x: x["similarity_diff"], reverse=True)
    by_label = {}
    for c in candidates:
        by_label[c["candidate_label"]] = by_label.get(c["candidate_label"], 0) + 1

    return {
        "status": "ok",
        "market": market,
        "universe_scanned": len(syms),
        "start_offset": start_offset,
        "total_eligible": total_eligible,
        "valid_pre_features_used": len(positive_library),
        "orphan_pre_features_excluded": orphan_count,
        "candidates_count": len(candidates),
        "by_label": by_label,
        "candidates_top50": candidates[:50],
    }
