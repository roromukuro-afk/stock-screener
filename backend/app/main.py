"""FastAPIエントリポイント"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from app.database import init_db, get_db_info
from app.routers import dashboard, screening, stocks, exclusions, export, backtest, settings as settings_router, universe as universe_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="短期急騰3000円以下AIスクリーナー",
    description="日本株・米国株・ADRを対象とした短期急騰パターン分析・学習ツール。投資助言ではありません。",
    version="1.0.0",
    lifespan=lifespan,
)


_default_origins = "http://localhost:3000,http://127.0.0.1:3000"
_origins_env = os.getenv("ALLOWED_ORIGINS", _default_origins).strip()
allow_origin_regex = os.getenv("ALLOWED_ORIGIN_REGEX", None)

# "*" を指定された場合は全許可、それ以外はカンマ区切りリスト
if _origins_env == "*":
    allow_origins = ["*"]
    # "*" のときは allow_credentials=True にできないため False にする
    allow_credentials = False
else:
    allow_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]
    allow_credentials = True

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_origin_regex=allow_origin_regex,
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(dashboard.router)
app.include_router(screening.router)
app.include_router(stocks.router)
app.include_router(exclusions.router)
app.include_router(export.router)
app.include_router(backtest.router)
app.include_router(settings_router.router)
app.include_router(universe_router.router)


@app.get("/")
def root():
    return {
        "name": "短期急騰3000円以下AIスクリーナー",
        "version": "1.0.0",
        "disclaimer": "これは投資助言ではありません。分析・学習目的のツールです。最終判断はユーザー自身が行ってください。",
        "docs": "/docs",
        "health": "/api/health",
        "status": "/api/status",
    }


@app.get("/api/status")
def status():
    db_info = get_db_info()
    return {
        "environment": os.getenv("APP_ENV", "local"),
        "database": db_info,
        "sample_mode": os.getenv("SAMPLE_MODE", "false").lower() == "true",
        "yfinance_enabled": os.getenv("YFINANCE_ENABLED", "true").lower() == "true",
        "allowed_origins": allow_origins,
        "default_usdjpy": float(os.getenv("DEFAULT_USDJPY", "155")),
    }
