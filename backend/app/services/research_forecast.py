"""Long-horizon Deep Research forecast verification.

This service verifies the 1w/1m/3m/6m/1y center-price forecasts produced by
company/ETF research. It is deliberately separate from the short-term surge
prediction reviewer.

Evaluation rule:
- target date is calendar-based from the point-in-time analysis date;
- actual price is the first trading-day close ON OR AFTER that target date;
- stock splits between analysis and evaluation are normalized back to the
  analysis-date share basis;
- cash dividends are not adjusted because the research forecast is a price
  forecast, not a total-return forecast.
"""
from __future__ import annotations

import calendar
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import quote

import requests
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.research_forecast import ResearchForecast, ResearchForecastCheckpoint
from app.services.price_fetcher import get_stock_data


HORIZON_SPECS = {
    "1w": {"label": "1週間", "days": 7, "months": 0},
    "1m": {"label": "1か月", "days": 0, "months": 1},
    "3m": {"label": "3か月", "days": 0, "months": 3},
    "6m": {"label": "6か月", "days": 0, "months": 6},
    "1y": {"label": "1年", "days": 0, "months": 12},
}
HORIZON_ORDER = {h: i for i, h in enumerate(HORIZON_SPECS)}
RETURN_PRICE_MISMATCH_TOLERANCE_PP = 0.25


def normalize_yahoo_symbol(symbol: str, market: str = "JP") -> str:
    symbol = (symbol or "").strip()
    market = (market or "JP").upper()
    if not symbol:
        raise ValueError("symbol is required")
    if market == "JP" and "." not in symbol:
        return f"{symbol}.T"
    return symbol


def _parse_analysis_date(analysis_asof: str) -> date:
    if not analysis_asof:
        raise ValueError("analysis_asof is required")
    raw = analysis_asof.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError:
        try:
            return date.fromisoformat(raw[:10])
        except ValueError as exc:
            raise ValueError(f"invalid analysis_asof: {analysis_asof}") from exc


def _add_months(d: date, months: int) -> date:
    month_index = (d.year * 12 + (d.month - 1)) + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    day = min(d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def target_date_for_horizon(analysis_date: date, horizon: str) -> date:
    spec = HORIZON_SPECS.get(horizon)
    if not spec:
        raise ValueError(f"unsupported horizon: {horizon}")
    if spec["months"]:
        return _add_months(analysis_date, spec["months"])
    return analysis_date + timedelta(days=spec["days"])


def _history_period(analysis_date: date, today: Optional[date] = None) -> str:
    today = today or date.today()
    age_days = max(0, (today - analysis_date).days)
    if age_days <= 550:
        return "2y"
    if age_days <= 1700:
        return "5y"
    return "10y"


def _as_float(value, field: str, allow_none: bool = True) -> Optional[float]:
    if value is None:
        if allow_none:
            return None
        raise ValueError(f"{field} is required")
    try:
        v = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if not math.isfinite(v):
        raise ValueError(f"{field} must be finite")
    return v


def _normalize_forecast_point(point: Dict, base_price: float) -> Dict:
    horizon = (point.get("horizon") or "").strip()
    if horizon not in HORIZON_SPECS:
        raise ValueError(f"unsupported horizon: {horizon}")

    predicted_return = _as_float(point.get("predicted_return_pct"), "predicted_return_pct")
    predicted_price = _as_float(point.get("predicted_price"), "predicted_price")
    if predicted_return is None and predicted_price is None:
        raise ValueError(f"{horizon}: predicted_return_pct or predicted_price is required")

    if predicted_price is None:
        predicted_price = base_price * (1.0 + predicted_return / 100.0)
    if predicted_return is None:
        predicted_return = (predicted_price / base_price - 1.0) * 100.0

    if predicted_price <= 0:
        raise ValueError(f"{horizon}: predicted_price must be > 0")

    return_from_price = (predicted_price / base_price - 1.0) * 100.0
    mismatch = abs(return_from_price - predicted_return)
    if mismatch > RETURN_PRICE_MISMATCH_TOLERANCE_PP:
        raise ValueError(
            f"{horizon}: predicted_return_pct and predicted_price disagree by "
            f"{mismatch:.3f} percentage points"
        )

    center_low = _as_float(point.get("center_range_low"), "center_range_low")
    center_high = _as_float(point.get("center_range_high"), "center_range_high")
    if center_low is not None and center_high is not None and center_low > center_high:
        raise ValueError(f"{horizon}: center_range_low must be <= center_range_high")

    return {
        "horizon": horizon,
        "horizon_label": HORIZON_SPECS[horizon]["label"],
        "predicted_return_pct": predicted_return,
        "predicted_price": predicted_price,
        "center_range_low": center_low,
        "center_range_high": center_high,
        "upside_reference_price": _as_float(point.get("upside_reference_price"), "upside_reference_price"),
        "downside_reference_price": _as_float(point.get("downside_reference_price"), "downside_reference_price"),
        "confidence": point.get("confidence"),
        "rationale": point.get("rationale"),
    }


def save_research_forecast(payload: Dict) -> Dict:
    """Persist one point-in-time research forecast and its horizon checkpoints."""
    symbol = (payload.get("symbol") or "").strip()
    market = (payload.get("market") or "JP").upper()
    analysis_asof = (payload.get("analysis_asof") or "").strip()
    analysis_date = _parse_analysis_date(analysis_asof)
    base_price = _as_float(payload.get("base_price"), "base_price", allow_none=False)
    if base_price <= 0:
        raise ValueError("base_price must be > 0")

    yahoo_symbol = (payload.get("yahoo_symbol") or "").strip() or normalize_yahoo_symbol(symbol, market)
    version = (payload.get("forecast_version") or "deep-research-v1").strip()
    replace_existing = bool(payload.get("replace_existing", False))

    points_raw = payload.get("forecasts") or []
    if not isinstance(points_raw, list) or not points_raw:
        raise ValueError("forecasts must be a non-empty list")

    points = [_normalize_forecast_point(p or {}, base_price) for p in points_raw]
    horizons = [p["horizon"] for p in points]
    if len(horizons) != len(set(horizons)):
        raise ValueError("duplicate horizon in forecasts")

    db: Session = SessionLocal()
    try:
        existing = (
            db.query(ResearchForecast)
            .filter(ResearchForecast.symbol == symbol)
            .filter(ResearchForecast.analysis_asof == analysis_asof)
            .filter(ResearchForecast.forecast_version == version)
            .first()
        )
        if existing and not replace_existing:
            return {
                "status": "exists",
                "forecast_id": existing.id,
                "message": "same symbol/analysis_asof/forecast_version already saved",
            }

        if existing:
            db.query(ResearchForecastCheckpoint).filter(
                ResearchForecastCheckpoint.forecast_id == existing.id
            ).delete()
            row = existing
        else:
            row = ResearchForecast()
            db.add(row)

        row.symbol = symbol
        row.yahoo_symbol = yahoo_symbol
        row.name = payload.get("name")
        row.market = market
        row.currency = payload.get("currency") or ("JPY" if market == "JP" else "USD")
        row.analysis_asof = analysis_asof
        row.analysis_date = analysis_date.isoformat()
        row.timezone = payload.get("timezone") or "Asia/Tokyo"
        row.forecast_version = version
        row.base_price = base_price
        row.base_price_date = payload.get("base_price_date") or analysis_date.isoformat()
        row.base_price_type = payload.get("base_price_type")
        row.base_price_source = payload.get("base_price_source")
        row.source_label = payload.get("source_label") or "ChatGPT Deep Research"
        row.source_reference = payload.get("source_reference")
        row.notes = payload.get("notes")
        row.status = "open"
        db.flush()

        for p in sorted(points, key=lambda x: HORIZON_ORDER[x["horizon"]]):
            target_date = target_date_for_horizon(analysis_date, p["horizon"])
            db.add(ResearchForecastCheckpoint(
                forecast_id=row.id,
                symbol=symbol,
                horizon=p["horizon"],
                horizon_label=p["horizon_label"],
                target_calendar_date=target_date.isoformat(),
                evaluation_policy="first_trading_day_on_or_after_target",
                predicted_return_pct=p["predicted_return_pct"],
                predicted_price=p["predicted_price"],
                center_range_low=p["center_range_low"],
                center_range_high=p["center_range_high"],
                upside_reference_price=p["upside_reference_price"],
                downside_reference_price=p["downside_reference_price"],
                confidence=p["confidence"],
                rationale=p["rationale"],
                status="pending",
            ))

        db.commit()
        return {
            "status": "ok",
            "forecast_id": row.id,
            "symbol": symbol,
            "analysis_asof": analysis_asof,
            "base_price": base_price,
            "checkpoints": len(points),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _split_ratio(event: Dict) -> Optional[float]:
    try:
        numerator = event.get("numerator")
        denominator = event.get("denominator")
        if numerator is not None and denominator not in (None, 0, "0"):
            ratio = float(numerator) / float(denominator)
            return ratio if ratio > 0 else None
    except (TypeError, ValueError, ZeroDivisionError):
        pass

    raw = str(event.get("splitRatio") or "").strip()
    for sep in (":", "/"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            try:
                ratio = float(left) / float(right)
                return ratio if ratio > 0 else None
            except (TypeError, ValueError, ZeroDivisionError):
                return None
    return None


def fetch_split_events(symbol: str, period: str = "2y") -> Tuple[List[Dict], str]:
    """Return Yahoo split events as [{date, ratio}], plus fetch status."""
    allowed_periods = {"1y", "2y", "5y", "10y", "max"}
    yf_range = period if period in allowed_periods else "2y"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol, safe='')}"
    params = {"interval": "1d", "range": yf_range, "events": "splits"}
    try:
        response = requests.get(
            url,
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=15,
        )
        if response.status_code != 200:
            return [], f"http_{response.status_code}"
        result = (response.json().get("chart") or {}).get("result") or []
        if not result:
            return [], "no_result"
        splits = (((result[0].get("events") or {}).get("splits")) or {})
        out = []
        for event in splits.values():
            ratio = _split_ratio(event or {})
            if not ratio:
                continue
            epoch = (event or {}).get("date")
            if epoch is None:
                continue
            try:
                event_date = datetime.fromtimestamp(float(epoch)).date().isoformat()
            except (TypeError, ValueError, OSError, OverflowError):
                continue
            out.append({"date": event_date, "ratio": ratio})
        out.sort(key=lambda x: x["date"])
        return out, "ok"
    except Exception as exc:
        return [], f"error:{type(exc).__name__}"


def split_factor_between(events: Iterable[Dict], start_date: str, end_date: str) -> float:
    factor = 1.0
    for event in events:
        d = str(event.get("date") or "")
        if start_date < d <= end_date:
            try:
                ratio = float(event.get("ratio"))
            except (TypeError, ValueError):
                continue
            if ratio > 0:
                factor *= ratio
    return factor


def compute_accuracy_metrics(
    base_price: float,
    predicted_return_pct: float,
    predicted_price: float,
    actual_price_comparable: float,
) -> Dict:
    actual_return_pct = (actual_price_comparable / base_price - 1.0) * 100.0
    price_error = actual_price_comparable - predicted_price
    absolute_price_error = abs(price_error)
    forecast_error_pct = (actual_price_comparable / predicted_price - 1.0) * 100.0
    absolute_percentage_error_pct = (
        abs(actual_price_comparable - predicted_price) / actual_price_comparable * 100.0
        if actual_price_comparable != 0 else None
    )
    return_error_pct_points = actual_return_pct - predicted_return_pct

    def sign(v: float) -> int:
        if v > 0:
            return 1
        if v < 0:
            return -1
        return 0

    return {
        "actual_return_pct": actual_return_pct,
        "price_error": price_error,
        "absolute_price_error": absolute_price_error,
        "forecast_error_pct": forecast_error_pct,
        "absolute_percentage_error_pct": absolute_percentage_error_pct,
        "return_error_pct_points": return_error_pct_points,
        "direction_match": sign(predicted_return_pct) == sign(actual_return_pct),
    }


def _checkpoint_to_dict(row: ResearchForecastCheckpoint) -> Dict:
    return {
        "id": row.id,
        "horizon": row.horizon,
        "horizon_label": row.horizon_label,
        "target_calendar_date": row.target_calendar_date,
        "evaluation_policy": row.evaluation_policy,
        "predicted_return_pct": row.predicted_return_pct,
        "predicted_price": row.predicted_price,
        "center_range_low": row.center_range_low,
        "center_range_high": row.center_range_high,
        "upside_reference_price": row.upside_reference_price,
        "downside_reference_price": row.downside_reference_price,
        "confidence": row.confidence,
        "rationale": row.rationale,
        "actual_check_date": row.actual_check_date,
        "actual_close_raw": row.actual_close_raw,
        "split_adjustment_factor": row.split_adjustment_factor,
        "actual_close_comparable": row.actual_close_comparable,
        "actual_return_pct": row.actual_return_pct,
        "price_error": row.price_error,
        "absolute_price_error": row.absolute_price_error,
        "forecast_error_pct": row.forecast_error_pct,
        "absolute_percentage_error_pct": row.absolute_percentage_error_pct,
        "return_error_pct_points": row.return_error_pct_points,
        "direction_match": row.direction_match,
        "center_range_hit": row.center_range_hit,
        "outer_range_hit": row.outer_range_hit,
        "status": row.status,
        "data_source": row.data_source,
        "last_error": row.last_error,
        "evaluated_at": row.evaluated_at.isoformat() if row.evaluated_at else None,
    }


def _forecast_to_dict(row: ResearchForecast, checkpoints: Optional[List[ResearchForecastCheckpoint]] = None) -> Dict:
    out = {
        "id": row.id,
        "symbol": row.symbol,
        "yahoo_symbol": row.yahoo_symbol,
        "name": row.name,
        "market": row.market,
        "currency": row.currency,
        "analysis_asof": row.analysis_asof,
        "analysis_date": row.analysis_date,
        "timezone": row.timezone,
        "forecast_version": row.forecast_version,
        "base_price": row.base_price,
        "base_price_date": row.base_price_date,
        "base_price_type": row.base_price_type,
        "base_price_source": row.base_price_source,
        "source_label": row.source_label,
        "source_reference": row.source_reference,
        "notes": row.notes,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    if checkpoints is not None:
        out["checkpoints"] = [
            _checkpoint_to_dict(c)
            for c in sorted(checkpoints, key=lambda c: HORIZON_ORDER.get(c.horizon, 999))
        ]
    return out


def get_research_forecast(forecast_id: int) -> Optional[Dict]:
    db: Session = SessionLocal()
    try:
        row = db.query(ResearchForecast).filter(ResearchForecast.id == forecast_id).first()
        if not row:
            return None
        checkpoints = db.query(ResearchForecastCheckpoint).filter(
            ResearchForecastCheckpoint.forecast_id == forecast_id
        ).all()
        return _forecast_to_dict(row, checkpoints)
    finally:
        db.close()


def list_research_forecasts(limit: int = 200, symbol: Optional[str] = None, status: Optional[str] = None) -> Dict:
    db: Session = SessionLocal()
    try:
        q = db.query(ResearchForecast)
        if symbol:
            q = q.filter(ResearchForecast.symbol == symbol)
        if status:
            q = q.filter(ResearchForecast.status == status)
        total = q.count()
        rows = q.order_by(ResearchForecast.id.desc()).limit(limit).all()
        items = []
        for row in rows:
            cps = db.query(ResearchForecastCheckpoint).filter(
                ResearchForecastCheckpoint.forecast_id == row.id
            ).all()
            d = _forecast_to_dict(row)
            d["checkpoint_count"] = len(cps)
            d["evaluated_count"] = sum(1 for c in cps if c.status == "evaluated")
            d["pending_count"] = sum(1 for c in cps if c.status != "evaluated")
            d["next_pending_target_date"] = min(
                (c.target_calendar_date for c in cps if c.status != "evaluated"),
                default=None,
            )
            items.append(d)
        return {"total": total, "items": items}
    finally:
        db.close()


def delete_research_forecast(forecast_id: int) -> bool:
    db: Session = SessionLocal()
    try:
        db.query(ResearchForecastCheckpoint).filter(
            ResearchForecastCheckpoint.forecast_id == forecast_id
        ).delete()
        deleted = db.query(ResearchForecast).filter(ResearchForecast.id == forecast_id).delete()
        db.commit()
        return deleted > 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_research_forecast(forecast_id: int, today: Optional[date] = None) -> Dict:
    today = today or date.today()
    db: Session = SessionLocal()
    try:
        forecast = db.query(ResearchForecast).filter(ResearchForecast.id == forecast_id).first()
        if not forecast:
            return {"status": "failed", "error": "forecast not found", "forecast_id": forecast_id}
        if forecast.status == "cancelled":
            return {"status": "skipped", "reason": "cancelled", "forecast_id": forecast_id}

        checkpoints = db.query(ResearchForecastCheckpoint).filter(
            ResearchForecastCheckpoint.forecast_id == forecast_id
        ).all()
        due = [
            c for c in checkpoints
            if c.status != "evaluated" and c.target_calendar_date <= today.isoformat()
        ]
        if not due:
            return {"status": "no_due_checkpoints", "forecast_id": forecast_id, "updated": 0}

        analysis_date = date.fromisoformat(forecast.analysis_date)
        period = _history_period(analysis_date, today)
        df = get_stock_data(forecast.yahoo_symbol, period=period, market=forecast.market)
        if df is None or df.empty:
            return {
                "status": "failed",
                "error": "price data unavailable",
                "forecast_id": forecast_id,
                "updated": 0,
            }

        df = df.copy()
        df["date"] = df["date"].astype(str).str[:10]
        df = df.sort_values("date").reset_index(drop=True)
        split_events, split_status = fetch_split_events(forecast.yahoo_symbol, period=period)

        updated = 0
        pending_no_data = 0
        for checkpoint in due:
            candidates = df[df["date"] >= checkpoint.target_calendar_date]
            if candidates.empty:
                checkpoint.last_error = "target date has passed but no trading-day close is available yet"
                pending_no_data += 1
                continue

            row = candidates.iloc[0]
            actual_date = str(row["date"])
            try:
                actual_close_raw = float(row["close"])
            except (TypeError, ValueError):
                checkpoint.status = "error"
                checkpoint.last_error = "non-numeric close price"
                continue
            if not math.isfinite(actual_close_raw) or actual_close_raw <= 0:
                checkpoint.status = "error"
                checkpoint.last_error = "invalid close price"
                continue

            split_factor = split_factor_between(split_events, forecast.analysis_date, actual_date)
            actual_comparable = actual_close_raw * split_factor
            metrics = compute_accuracy_metrics(
                forecast.base_price,
                checkpoint.predicted_return_pct,
                checkpoint.predicted_price,
                actual_comparable,
            )

            checkpoint.actual_check_date = actual_date
            checkpoint.actual_close_raw = actual_close_raw
            checkpoint.split_adjustment_factor = split_factor
            checkpoint.actual_close_comparable = actual_comparable
            checkpoint.actual_return_pct = metrics["actual_return_pct"]
            checkpoint.price_error = metrics["price_error"]
            checkpoint.absolute_price_error = metrics["absolute_price_error"]
            checkpoint.forecast_error_pct = metrics["forecast_error_pct"]
            checkpoint.absolute_percentage_error_pct = metrics["absolute_percentage_error_pct"]
            checkpoint.return_error_pct_points = metrics["return_error_pct_points"]
            checkpoint.direction_match = metrics["direction_match"]

            if checkpoint.center_range_low is not None and checkpoint.center_range_high is not None:
                checkpoint.center_range_hit = (
                    checkpoint.center_range_low <= actual_comparable <= checkpoint.center_range_high
                )
            else:
                checkpoint.center_range_hit = None

            if (
                checkpoint.downside_reference_price is not None
                and checkpoint.upside_reference_price is not None
            ):
                lo = min(checkpoint.downside_reference_price, checkpoint.upside_reference_price)
                hi = max(checkpoint.downside_reference_price, checkpoint.upside_reference_price)
                checkpoint.outer_range_hit = lo <= actual_comparable <= hi
            else:
                checkpoint.outer_range_hit = None

            checkpoint.status = "evaluated"
            checkpoint.data_source = f"Yahoo Finance daily close; split_events={split_status}"
            checkpoint.last_error = None
            checkpoint.evaluated_at = datetime.utcnow()
            updated += 1

        if checkpoints and all(c.status == "evaluated" for c in checkpoints):
            forecast.status = "complete"
        else:
            forecast.status = "open"

        db.commit()
        return {
            "status": "ok",
            "forecast_id": forecast_id,
            "symbol": forecast.symbol,
            "updated": updated,
            "pending_no_data": pending_no_data,
            "split_events_status": split_status,
            "split_events_used": split_events,
        }
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def update_all_due_forecasts(limit: int = 200, today: Optional[date] = None) -> Dict:
    today = today or date.today()
    db: Session = SessionLocal()
    try:
        rows = (
            db.query(ResearchForecast)
            .filter(ResearchForecast.status == "open")
            .order_by(ResearchForecast.id.asc())
            .limit(limit)
            .all()
        )
        ids = [r.id for r in rows]
    finally:
        db.close()

    forecasts_updated = 0
    checkpoints_updated = 0
    failed = 0
    details = []
    for forecast_id in ids:
        try:
            result = update_research_forecast(forecast_id, today=today)
            details.append(result)
            n = int(result.get("updated") or 0)
            if n > 0:
                forecasts_updated += 1
                checkpoints_updated += n
        except Exception as exc:
            failed += 1
            details.append({
                "status": "failed",
                "forecast_id": forecast_id,
                "error": f"{type(exc).__name__}: {str(exc)[:200]}",
            })

    return {
        "status": "ok" if failed == 0 else "partial",
        "today": today.isoformat(),
        "forecasts_checked": len(ids),
        "forecasts_updated": forecasts_updated,
        "checkpoints_updated": checkpoints_updated,
        "failed": failed,
        "details": details,
    }


def _rate(values: List[Optional[bool]]) -> Optional[float]:
    usable = [v for v in values if v is not None]
    if not usable:
        return None
    return sum(1 for v in usable if v) / len(usable) * 100.0


def _avg(values: List[Optional[float]]) -> Optional[float]:
    usable = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not usable:
        return None
    return sum(usable) / len(usable)


def _median(values: List[Optional[float]]) -> Optional[float]:
    usable = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    return median(usable) if usable else None


def _summarize_group(rows: List[ResearchForecastCheckpoint]) -> Dict:
    return {
        "evaluated_count": len(rows),
        "mean_predicted_return_pct": _avg([r.predicted_return_pct for r in rows]),
        "mean_actual_return_pct": _avg([r.actual_return_pct for r in rows]),
        "mean_absolute_percentage_error_pct": _avg([r.absolute_percentage_error_pct for r in rows]),
        "median_absolute_percentage_error_pct": _median([r.absolute_percentage_error_pct for r in rows]),
        "mean_absolute_return_error_pct_points": _avg([
            abs(r.return_error_pct_points) if r.return_error_pct_points is not None else None for r in rows
        ]),
        "mean_signed_return_error_pct_points": _avg([r.return_error_pct_points for r in rows]),
        "direction_accuracy_pct": _rate([r.direction_match for r in rows]),
        "center_range_hit_rate_pct": _rate([r.center_range_hit for r in rows]),
        "outer_range_hit_rate_pct": _rate([r.outer_range_hit for r in rows]),
    }


def accuracy_summary(symbol: Optional[str] = None) -> Dict:
    db: Session = SessionLocal()
    try:
        q = (
            db.query(ResearchForecastCheckpoint)
            .join(ResearchForecast, ResearchForecast.id == ResearchForecastCheckpoint.forecast_id)
            .filter(ResearchForecastCheckpoint.status == "evaluated")
        )
        if symbol:
            q = q.filter(ResearchForecast.symbol == symbol)
        rows = q.all()

        groups: Dict[str, List[ResearchForecastCheckpoint]] = defaultdict(list)
        for row in rows:
            groups[row.horizon].append(row)

        pending_due_q = (
            db.query(ResearchForecastCheckpoint)
            .join(ResearchForecast, ResearchForecast.id == ResearchForecastCheckpoint.forecast_id)
            .filter(ResearchForecast.status == "open")
            .filter(ResearchForecastCheckpoint.status != "evaluated")
            .filter(ResearchForecastCheckpoint.target_calendar_date <= date.today().isoformat())
        )
        if symbol:
            pending_due_q = pending_due_q.filter(ResearchForecast.symbol == symbol)
        pending_due = pending_due_q.count()

        upcoming_q = (
            db.query(ResearchForecastCheckpoint, ResearchForecast)
            .join(ResearchForecast, ResearchForecast.id == ResearchForecastCheckpoint.forecast_id)
            .filter(ResearchForecast.status == "open")
            .filter(ResearchForecastCheckpoint.status != "evaluated")
            .filter(ResearchForecastCheckpoint.target_calendar_date > date.today().isoformat())
        )
        if symbol:
            upcoming_q = upcoming_q.filter(ResearchForecast.symbol == symbol)
        upcoming_rows = upcoming_q.order_by(ResearchForecastCheckpoint.target_calendar_date.asc()).limit(20).all()

        by_horizon = {
            horizon: _summarize_group(groups[horizon])
            for horizon in HORIZON_SPECS
            if groups.get(horizon)
        }
        return {
            "symbol": symbol,
            "overall": _summarize_group(rows),
            "by_horizon": by_horizon,
            "pending_due_count": pending_due,
            "upcoming": [
                {
                    "forecast_id": forecast.id,
                    "symbol": forecast.symbol,
                    "horizon": checkpoint.horizon,
                    "target_calendar_date": checkpoint.target_calendar_date,
                    "predicted_price": checkpoint.predicted_price,
                    "predicted_return_pct": checkpoint.predicted_return_pct,
                }
                for checkpoint, forecast in upcoming_rows
            ],
        }
    finally:
        db.close()


def export_rows(symbol: Optional[str] = None) -> List[Dict]:
    db: Session = SessionLocal()
    try:
        q = (
            db.query(ResearchForecastCheckpoint, ResearchForecast)
            .join(ResearchForecast, ResearchForecast.id == ResearchForecastCheckpoint.forecast_id)
        )
        if symbol:
            q = q.filter(ResearchForecast.symbol == symbol)
        rows = q.order_by(ResearchForecast.id.desc(), ResearchForecastCheckpoint.id.asc()).all()
        out = []
        for checkpoint, forecast in rows:
            d = {
                "forecast_id": forecast.id,
                "symbol": forecast.symbol,
                "name": forecast.name,
                "market": forecast.market,
                "analysis_asof": forecast.analysis_asof,
                "base_price": forecast.base_price,
                "forecast_version": forecast.forecast_version,
                "forecast_status": forecast.status,
            }
            d.update(_checkpoint_to_dict(checkpoint))
            out.append(d)
        return out
    finally:
        db.close()
