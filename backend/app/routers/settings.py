"""アプリ設定 API"""
import os
from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Optional
from app.db_repo import get_setting, set_setting, get_all_settings
from app.database import get_db_info
from app.services.price_fetcher import is_sample_mode, get_usd_jpy

router = APIRouter(prefix="/api/settings", tags=["settings"])


DEFAULTS = {
    "price_limit": "3000",
    "min_vol_jp": "30000",
    "min_vol_us": "100000",
    "min_score": "0",
    "include_adr": "false",
    "sample_mode": "false",
    "default_usdjpy": "155",
    "apply_exclusion_list": "true",
    "max_symbols": "0",
}


class SettingUpdate(BaseModel):
    key: str
    value: str


class SettingsBulk(BaseModel):
    settings: Dict[str, str]


@router.get("")
def list_settings():
    saved = get_all_settings()
    merged = {**DEFAULTS, **saved}
    return {
        "settings": merged,
        "defaults": DEFAULTS,
        "env": {
            "APP_ENV": os.getenv("APP_ENV", "local"),
            "ALLOWED_ORIGINS": os.getenv("ALLOWED_ORIGINS", ""),
            "DEFAULT_USDJPY": os.getenv("DEFAULT_USDJPY", "155"),
            "SAMPLE_MODE_ENV": os.getenv("SAMPLE_MODE", "false"),
            "YFINANCE_ENABLED": os.getenv("YFINANCE_ENABLED", "true"),
        },
        "runtime": {
            "sample_mode_active": is_sample_mode(),
            "usd_jpy": get_usd_jpy(),
            "db": get_db_info(),
        },
    }


@router.post("")
def update_setting(item: SettingUpdate):
    set_setting(item.key, item.value)
    return {"ok": True, "key": item.key, "value": item.value}


@router.post("/bulk")
def update_settings_bulk(payload: SettingsBulk):
    for k, v in payload.settings.items():
        set_setting(k, str(v))
    return {"ok": True, "saved": len(payload.settings)}


@router.get("/deploy-status")
def deploy_status():
    return {
        "environment": os.getenv("APP_ENV", "local"),
        "allowed_origins": [o.strip() for o in os.getenv("ALLOWED_ORIGINS", "http://localhost:3000").split(",")],
        "frontend_hint_url": os.getenv("FRONTEND_URL", ""),
        "backend_hint_url": os.getenv("BACKEND_URL", ""),
        "database": get_db_info(),
        "sample_mode_active": is_sample_mode(),
        "yfinance_enabled": os.getenv("YFINANCE_ENABLED", "true").lower() == "true",
        "default_usdjpy": float(os.getenv("DEFAULT_USDJPY", "155")),
    }
