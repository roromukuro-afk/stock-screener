"""API for long-horizon Deep Research forecast verification."""
import csv
import io
import os
from typing import Dict, List, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.services import research_forecast as service
from app.utils import clean_for_json


router = APIRouter(prefix="/api/research-forecast", tags=["research-forecast"])


class ForecastPointRequest(BaseModel):
    horizon: str
    predicted_return_pct: Optional[float] = None
    predicted_price: Optional[float] = None
    center_range_low: Optional[float] = None
    center_range_high: Optional[float] = None
    upside_reference_price: Optional[float] = None
    downside_reference_price: Optional[float] = None
    confidence: Optional[str] = None
    rationale: Optional[str] = None


class SaveResearchForecastRequest(BaseModel):
    symbol: str
    yahoo_symbol: Optional[str] = None
    name: Optional[str] = None
    market: str = "JP"
    currency: Optional[str] = None
    analysis_asof: str
    timezone: str = "Asia/Tokyo"
    base_price: float
    base_price_date: Optional[str] = None
    base_price_type: Optional[str] = None
    base_price_source: Optional[str] = None
    forecast_version: str = "deep-research-v1"
    source_label: str = "ChatGPT Deep Research"
    source_reference: Optional[str] = None
    notes: Optional[str] = None
    replace_existing: bool = False
    forecasts: List[ForecastPointRequest]


def _check_secret(x_cron_secret: Optional[str], authorization: Optional[str]):
    """Require the same CRON_SECRET used by the automation endpoints when configured."""
    required = os.getenv("CRON_SECRET", "")
    if not required:
        return
    provided = x_cron_secret or ""
    if not provided and authorization and authorization.lower().startswith("bearer "):
        provided = authorization[7:]
    if provided != required:
        raise HTTPException(403, "invalid CRON_SECRET")


@router.post("/save")
def save_forecast(req: SaveResearchForecastRequest):
    try:
        payload: Dict = req.model_dump()
        payload["forecasts"] = [p.model_dump() for p in req.forecasts]
        return clean_for_json(service.save_research_forecast(payload))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/list")
def list_forecasts(limit: int = 200, symbol: Optional[str] = None, status: Optional[str] = None):
    return clean_for_json(service.list_research_forecasts(limit=limit, symbol=symbol, status=status))


@router.get("/summary")
def summary(symbol: Optional[str] = None):
    return clean_for_json(service.accuracy_summary(symbol=symbol))


@router.get("/export/csv")
def export_csv(symbol: Optional[str] = None):
    rows = service.export_rows(symbol=symbol)
    buf = io.StringIO()
    if rows:
        fieldnames = list(rows[0].keys())
        writer = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    else:
        buf.write("forecast_id,symbol,horizon,status\n")
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": "attachment; filename=research_forecast_accuracy.csv"},
    )


@router.post("/update-due")
def update_due(
    limit: int = 200,
    x_cron_secret: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_secret(x_cron_secret, authorization)
    return clean_for_json(service.update_all_due_forecasts(limit=limit))


@router.post("/{forecast_id}/update")
def update_one(
    forecast_id: int,
    x_cron_secret: Optional[str] = Header(None),
    authorization: Optional[str] = Header(None),
):
    _check_secret(x_cron_secret, authorization)
    return clean_for_json(service.update_research_forecast(forecast_id))


@router.get("/{forecast_id}")
def get_forecast(forecast_id: int):
    result = service.get_research_forecast(forecast_id)
    if not result:
        raise HTTPException(404, "Not found")
    return clean_for_json(result)


@router.delete("/{forecast_id}")
def delete_forecast(forecast_id: int):
    if not service.delete_research_forecast(forecast_id):
        raise HTTPException(404, "Not found")
    return {"deleted": True}
