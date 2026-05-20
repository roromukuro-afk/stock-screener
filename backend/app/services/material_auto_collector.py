"""TDnet / EDGAR / IR / ニュースからの材料自動収集

毎日 cron から呼び出して material_events を増やす。
SNS や材料不明は強くは加点しない設計。
"""
import logging
import re
import time
import hashlib
from typing import Dict, List, Optional
from datetime import datetime, date, timedelta
import requests

from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models.models import MaterialEvent, MaterialSourceCache, AutomationError
from app.services.material_research import _classify_text, _classify_url

logger = logging.getLogger(__name__)


USER_AGENT = "Mozilla/5.0 (compatible; stock-screener/1.0; +https://stock-screener-two-sandy.vercel.app)"
SEC_USER_AGENT = "stock-screener research-only contact-via-github"


# =========================================
# TDnet (Tokyo Stock Exchange timely disclosure)
# =========================================
def fetch_tdnet_today() -> List[Dict]:
    """TDnet 当日開示一覧を取得。タイトル一覧 → 銘柄ごとに分類

    TDnet公式は CSV/HTML を提供。簡易的に I-Search エンドポイントを叩く。
    取得失敗時は空list返す。
    """
    # 当日 yyyy-mm-dd を YYYYMMDD 形式に
    today = date.today().strftime("%Y%m%d")
    # TDnet I-Searchの "リアルタイム" 一覧 URL (公開)
    # 例: https://www.release.tdnet.info/inbs/I_list_001_20260519.html
    items: List[Dict] = []
    for page in range(1, 5):  # 最大4ページ
        url = f"https://www.release.tdnet.info/inbs/I_list_{page:03d}_{today}.html"
        try:
            r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
            if r.status_code != 200:
                continue
            # HTMLからtable行を抽出 (簡易)
            html = r.text
            # 行パターン: 時刻 / 4桁コード / 銘柄名 / タイトル / PDF URL
            row_pattern = re.compile(
                r'<td[^>]*>(\d{2}:\d{2})</td>\s*<td[^>]*>(\d{4})</td>\s*<td[^>]*>([^<]+)</td>\s*<td[^>]*><a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>',
                re.DOTALL,
            )
            for m in row_pattern.finditer(html):
                tm, code, name, pdf_path, title = m.groups()
                items.append({
                    "symbol": f"{code}.T",
                    "code": code,
                    "name": name.strip(),
                    "time": tm,
                    "title": title.strip(),
                    "source_url": f"https://www.release.tdnet.info/inbs/{pdf_path}",
                    "published_at": f"{date.today().isoformat()} {tm}",
                    "source_type": "tdnet",
                    "source_rank": "一次",
                    "market": "JP",
                })
            if not row_pattern.search(html):
                # ページが空っぽ
                break
        except Exception as e:
            logger.warning(f"TDnet fetch page {page} failed: {e}")
            continue
    return items


# =========================================
# SEC EDGAR
# =========================================
def fetch_edgar_submissions(cik: str) -> Optional[Dict]:
    """SEC EDGAR submissions API"""
    cik_padded = str(cik).zfill(10)
    url = f"https://data.sec.gov/submissions/CIK{cik_padded}.json"
    try:
        r = requests.get(url, headers={"User-Agent": SEC_USER_AGENT}, timeout=15)
        if r.status_code != 200:
            return None
        return r.json()
    except Exception as e:
        logger.warning(f"EDGAR fetch CIK{cik_padded} failed: {e}")
        return None


def fetch_edgar_recent_filings_by_ticker(ticker: str, lookback_days: int = 7) -> List[Dict]:
    """tickerから直近 lookback_days の filings を取得"""
    # ticker -> CIK lookup
    try:
        ticker_map_url = "https://www.sec.gov/files/company_tickers.json"
        r = requests.get(ticker_map_url, headers={"User-Agent": SEC_USER_AGENT}, timeout=15)
        if r.status_code != 200:
            return []
        data = r.json()
        cik = None
        for _, entry in data.items():
            if isinstance(entry, dict) and entry.get("ticker", "").upper() == ticker.upper():
                cik = str(entry.get("cik_str", ""))
                break
        if not cik:
            return []
    except Exception as e:
        logger.warning(f"EDGAR ticker map failed: {e}")
        return []

    sub = fetch_edgar_submissions(cik)
    if not sub:
        return []

    items = []
    recent = (sub.get("filings") or {}).get("recent") or {}
    accession = recent.get("accessionNumber") or []
    form = recent.get("form") or []
    filing_date = recent.get("filingDate") or []
    primary_doc = recent.get("primaryDocument") or []

    cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
    cik_clean = cik.lstrip("0") or "0"

    for i in range(min(len(accession), 50)):
        if filing_date[i] < cutoff:
            continue
        acc_no = accession[i].replace("-", "")
        url = f"https://www.sec.gov/Archives/edgar/data/{cik_clean}/{acc_no}/{primary_doc[i]}"
        items.append({
            "symbol": ticker.upper(),
            "code": ticker.upper(),
            "name": ticker.upper(),
            "title": f"{form[i]} filing ({filing_date[i]})",
            "form_type": form[i],
            "source_url": url,
            "published_at": filing_date[i],
            "source_type": "edgar",
            "source_rank": "一次",
            "market": "US",
            "accession_number": accession[i],
        })
    return items


# =========================================
# 保存
# =========================================
def _is_duplicate(symbol: str, source_url: str) -> bool:
    if not source_url:
        return False
    db: Session = SessionLocal()
    try:
        existing = (db.query(MaterialEvent)
                    .filter(MaterialEvent.symbol == symbol)
                    .filter(MaterialEvent.source_url == source_url)
                    .first())
        return existing is not None
    finally:
        db.close()


def _save_material_event(item: Dict) -> Optional[int]:
    if _is_duplicate(item["symbol"], item["source_url"]):
        return None

    # タイトルから分類
    title_text = (item.get("title") or "") + " " + (item.get("name") or "")
    classification = _classify_text(title_text)
    category = classification.get("catalyst_category") or "材料不明"
    risk_flags = classification.get("risk_flags", {})

    # ソースランクからスコア
    rank_score = {"一次": 80, "二次": 55, "三次": 30, "ユーザー入力": 25, "SNS": 10, "なし": 0}.get(
        item.get("source_rank") or "三次", 30
    )
    has_keywords = bool(classification.get("matched_keywords"))
    catalyst_quality = min(100, rank_score + (15 if has_keywords else 0))

    if category in ("テーマ波及", "政策/国策", "FDA/治験/承認", "大型契約"):
        catalyst_continuity = 60
    elif category in ("決算", "上方修正"):
        catalyst_continuity = 45
    elif category in ("M&A", "TOB"):
        catalyst_continuity = 70
    else:
        catalyst_continuity = 25

    catalyst_freshness = 80
    catalyst_surprise = 55 if has_keywords else 20
    theme_tailwind = 60 if category == "テーマ波及" else 20

    db: Session = SessionLocal()
    try:
        ev = MaterialEvent(
            symbol=item["symbol"],
            yahoo_symbol=item["symbol"],
            market=item.get("market") or "JP",
            title=item.get("title"),
            source_url=item.get("source_url"),
            source_type=item.get("source_type"),
            source_rank=item.get("source_rank"),
            published_at=item.get("published_at"),
            catalyst_category=category,
            catalyst_timing="T-1以前" if item.get("published_at") else "不明",
            catalyst_quality_score=catalyst_quality,
            catalyst_continuity_score=catalyst_continuity,
            catalyst_freshness_score=catalyst_freshness,
            catalyst_surprise_score=catalyst_surprise,
            theme_tailwind_score=theme_tailwind,
            material_confirmed=(item.get("source_rank") == "一次"),
            material_text=item.get("title"),
            ai_analysis=f"自動収集 by {item.get('source_type')} ({item.get('source_rank')})",
            risk_flags=risk_flags,
        )
        db.add(ev)
        db.commit()
        return ev.id
    except Exception as e:
        db.rollback()
        logger.warning(f"save material failed {item.get('symbol')}: {e}")
        return None
    finally:
        db.close()


# =========================================
# 自動収集ジョブ
# =========================================
def collect_jp_materials() -> Dict:
    """日本株材料自動収集 (TDnet)"""
    try:
        items = fetch_tdnet_today()
    except Exception as e:
        return {"status": "failed", "error": str(e), "fetched": 0, "saved": 0}

    saved = 0
    duplicate = 0
    for item in items:
        result = _save_material_event(item)
        if result:
            saved += 1
        else:
            duplicate += 1
    return {
        "status": "ok",
        "source": "tdnet",
        "fetched": len(items),
        "saved": saved,
        "duplicate": duplicate,
    }


def collect_us_materials(symbols: List[str] = None, max_symbols: int = 30) -> Dict:
    """米国株材料自動収集 (EDGAR)

    対象 ticker のみ filings を取得 (SEC submissions APIはCIK単位)
    """
    if symbols is None:
        # universe DBから eligible US 銘柄を取得
        from app.services import universe_db
        syms = universe_db.list_eligible_yahoo_symbols(
            markets=["US"], max_count=max_symbols, include_adr=False
        )
        symbols = [s["symbol"] for s in syms]

    total_fetched = 0
    saved = 0
    duplicate = 0
    failed = 0
    for ticker in symbols[:max_symbols]:
        try:
            items = fetch_edgar_recent_filings_by_ticker(ticker, lookback_days=7)
            total_fetched += len(items)
            for item in items:
                result = _save_material_event(item)
                if result:
                    saved += 1
                else:
                    duplicate += 1
            # SEC EDGAR は rate limit があるので少し待つ (10req/sec制限)
            time.sleep(0.15)
        except Exception as e:
            failed += 1
            # automation_errors に記録
            try:
                db = SessionLocal()
                db.add(AutomationError(
                    job_id=None, symbol=ticker, market="US",
                    step="collect_us_materials",
                    error_type=type(e).__name__,
                    error_message=str(e)[:300],
                ))
                db.commit(); db.close()
            except Exception:
                pass
    return {
        "status": "ok",
        "source": "edgar",
        "fetched": total_fetched,
        "saved": saved,
        "duplicate": duplicate,
        "failed": failed,
        "tickers_checked": min(len(symbols), max_symbols),
    }


def collect_all_materials_daily() -> Dict:
    """日次総合収集"""
    jp = collect_jp_materials()
    us = collect_us_materials(max_symbols=20)
    return {"status": "ok", "jp": jp, "us": us}
