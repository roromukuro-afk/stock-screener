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
# EDINET (金融庁・有価証券報告書 / 大量保有報告書 等)
# =========================================
def fetch_edinet_disclosures(target_date: Optional[str] = None, max_items: int = 150) -> List[Dict]:
    """EDINET 公式 JSON API から当日提出書類一覧を取得 (free, no auth)。
    secCode(4桁証券コード+チェックデジット) を持つ銘柄分のみ材料化。
    """
    if target_date is None:
        target_date = date.today().isoformat()
    items: List[Dict] = []
    try:
        url = f"https://disclosure.edinet-fsa.go.jp/api/v2/documents.json?date={target_date}&type=2"
        r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=20)
        if r.status_code != 200:
            return items
        results = (r.json() or {}).get("results") or []
        for d in results[:max_items]:
            sec_code = (d.get("secCode") or "").strip()
            if not sec_code or len(sec_code) < 4 or not sec_code[:4].isdigit():
                continue
            sym = sec_code[:4]
            doc_id = d.get("docID")
            doc_desc = (d.get("docDescription") or "").strip()
            filer_name = (d.get("filerName") or "").strip()
            submit_dt = d.get("submitDateTime") or target_date
            src_url = (f"https://disclosure.edinet-fsa.go.jp/api/v2/documents/{doc_id}?type=2"
                       if doc_id else f"edinet:{sec_code}-{submit_dt}")
            # docDescription から書類種別を抽出して source_type を細分化
            # 大量保有報告書 (5%ルール超え→需給に直接効く) / 役員報告書 (インサイダー動向)
            # /公開買付届出書 (M&A) は特に株価インパクトが大きい
            sub_type = "edinet"
            if "大量保有報告書" in doc_desc or "5%" in doc_desc:
                sub_type = "edinet_5pct_holding"
            elif "役員報告書" in doc_desc or "売却" in doc_desc or "取得" in doc_desc:
                sub_type = "edinet_insider"
            elif "公開買付" in doc_desc or "TOB" in doc_desc:
                sub_type = "edinet_tob"
            elif "有価証券届出書" in doc_desc or "発行登録" in doc_desc:
                sub_type = "edinet_issuance"  # 増資・新株予約権 → 希薄化リスク
            items.append({
                "symbol": sym, "code": sym, "name": filer_name,
                "title": f"{filer_name}: {doc_desc}" if filer_name else doc_desc,
                "source_url": src_url,
                "published_at": (submit_dt[:10] if submit_dt else target_date),
                "source_type": sub_type,
                "source_rank": "一次",  # EDINET は公式開示 → 一次
                "market": "JP",
            })
    except Exception as e:
        logger.warning(f"EDINET fetch failed: {e}")
    return items


# =========================================
# 汎用 RSS (Reuters / Nikkei 等) → universe マッチ
# =========================================
def fetch_rss_items(feed_url: str, max_items: int = 50) -> List[Dict]:
    """汎用 RSS 取得 (feedparser不要、stdlib のみ)"""
    items: List[Dict] = []
    try:
        r = requests.get(feed_url, headers={"User-Agent": USER_AGENT}, timeout=15)
        if r.status_code != 200:
            return items
        from xml.etree import ElementTree as ET
        try:
            root = ET.fromstring(r.content)
        except ET.ParseError:
            return items
        for it in list(root.iter("item"))[:max_items]:
            items.append({
                "title": (it.findtext("title") or "").strip(),
                "link": (it.findtext("link") or "").strip(),
                "pubDate": (it.findtext("pubDate") or "").strip(),
                "description": (it.findtext("description") or "").strip(),
            })
    except Exception as e:
        logger.warning(f"RSS fetch {feed_url} failed: {e}")
    return items


_JP_NEWS_FEEDS = [
    ("reuters_jp_business", "https://feeds.reuters.com/reuters/JPBusinessNews"),
    ("nikkei_top", "https://www.nikkei.com/rss/feed/nxt_feed_top.xml"),
    # Yahoo Finance JP: ロイター/日経/共同通信を集約
    ("yahoo_finance_jp", "https://news.yahoo.co.jp/rss/categories/business.xml"),
    ("yahoo_finance_jp_economy", "https://news.yahoo.co.jp/rss/categories/economy.xml"),
    # 個人投資家向け
    ("kabutan", "https://kabutan.jp/news/?b=top&category=&page=1.rss"),
    # IR最速プレスリリース
    ("prtimes_ir", "https://prtimes.jp/index.rdf"),
]
_US_NEWS_FEEDS = [
    ("reuters_us_business", "https://feeds.reuters.com/reuters/businessNews"),
    ("reuters_marketsnews", "https://feeds.reuters.com/news/wealth"),
    # SEC EDGAR の RSS (公式)
    ("sec_filings_8k", "https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&output=atom"),
]


def _normalize_pubdate(s: str) -> str:
    """RSS pubDate / EDINET 形式を YYYY-MM-DD に正規化。失敗時は今日。"""
    if not s:
        return date.today().isoformat()
    s = s.strip()
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    # RFC822: Mon, 30 May 2026 09:32:00 +0900
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt:
            return dt.date().isoformat()
    except Exception:
        pass
    # ISO with T
    if "T" in s:
        return s.split("T")[0]
    return date.today().isoformat()


def _build_name_to_sym_map(market: str) -> Dict[str, str]:
    try:
        from app.services import universe_db
        syms = universe_db.list_eligible_yahoo_symbols(markets=[market], max_count=0)
        m: Dict[str, str] = {}
        for s in syms:
            nm = (s.get("name") or "").strip()
            sym = s.get("symbol") or ""
            if nm and len(nm) >= 3 and sym:
                m[nm] = sym
        return m
    except Exception:
        return {}


def fetch_news_for_universe(market: str = "JP", max_feed_items: int = 50) -> List[Dict]:
    """主要RSS (Reuters / Nikkei / Yahoo) からタイトル＋本文を取得し、
    universe の銘柄名と一致する記事を材料イベント化。"""
    feeds = _JP_NEWS_FEEDS if market == "JP" else _US_NEWS_FEEDS
    name_to_sym = _build_name_to_sym_map(market)
    if not name_to_sym:
        return []
    out: List[Dict] = []
    seen = set()
    for src, url in feeds:
        try:
            for it in fetch_rss_items(url, max_items=max_feed_items):
                text_for_match = (it.get("title", "") or "") + " " + (it.get("description", "") or "")
                if len(text_for_match.strip()) < 4:
                    continue
                hit_sym = None
                hit_name = None
                for nm, sym in name_to_sym.items():
                    if nm in text_for_match:
                        hit_sym = sym
                        hit_name = nm
                        break
                if not hit_sym:
                    continue
                key = (hit_sym, it.get("link") or it.get("title"))
                if key in seen:
                    continue
                seen.add(key)
                out.append({
                    "symbol": hit_sym, "code": hit_sym, "name": hit_name,
                    "title": it.get("title"),
                    "source_url": it.get("link") or f"news:{src}/{hash(it.get('title') or '') & 0xffffffff}",
                    "published_at": _normalize_pubdate(it.get("pubDate") or ""),
                    "source_type": src,
                    "source_rank": "二次",  # 主要メディアは二次情報
                    "market": market,
                })
        except Exception as e:
            logger.warning(f"news feed {src} failed: {e}")
    return out


# =========================================
# 自動収集ジョブ
# =========================================
def collect_jp_materials() -> Dict:
    """日本株材料自動収集 (TDnet + EDINET + Reuters/Nikkei RSS)"""
    saved = 0
    duplicate = 0
    fetched_total = 0
    by_source = {}
    try:
        # 1) TDnet (適時開示)
        tdnet_items = fetch_tdnet_today()
        fetched_total += len(tdnet_items)
        s = d = 0
        for item in tdnet_items:
            r = _save_material_event(item)
            if r: s += 1
            else: d += 1
        saved += s; duplicate += d
        by_source["tdnet"] = {"fetched": len(tdnet_items), "saved": s, "duplicate": d}

        # 2) EDINET (公式開示)
        try:
            ed_items = fetch_edinet_disclosures()
            fetched_total += len(ed_items)
            s = d = 0
            for item in ed_items:
                r = _save_material_event(item)
                if r: s += 1
                else: d += 1
            saved += s; duplicate += d
            by_source["edinet"] = {"fetched": len(ed_items), "saved": s, "duplicate": d}
        except Exception as e:
            by_source["edinet"] = {"error": str(e)[:200]}

        # 3) 主要RSS (Reuters JP / Nikkei / Yahoo Finance) → universe マッチ
        try:
            news_items = fetch_news_for_universe(market="JP")
            fetched_total += len(news_items)
            s = d = 0
            for item in news_items:
                r = _save_material_event(item)
                if r: s += 1
                else: d += 1
            saved += s; duplicate += d
            by_source["news_jp"] = {"fetched": len(news_items), "saved": s, "duplicate": d}
        except Exception as e:
            by_source["news_jp"] = {"error": str(e)[:200]}

        return {
            "status": "ok", "sources": "tdnet+edinet+rss_jp",
            "fetched": fetched_total, "saved": saved, "duplicate": duplicate,
            "by_source": by_source,
        }
    except Exception as e:
        return {"status": "failed", "error": str(e),
                "fetched": fetched_total, "saved": saved,
                "by_source": by_source}


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
    # 追加: US主要RSSニュース (Reuters US business) → universe マッチ
    news_saved = 0; news_duplicate = 0; news_fetched = 0
    try:
        news_items = fetch_news_for_universe(market="US")
        news_fetched = len(news_items)
        for item in news_items:
            if _save_material_event(item):
                news_saved += 1
            else:
                news_duplicate += 1
    except Exception:
        pass

    return {
        "status": "ok",
        "sources": "edgar+rss_us",
        "fetched": total_fetched + news_fetched,
        "saved": saved + news_saved,
        "duplicate": duplicate + news_duplicate,
        "failed": failed,
        "tickers_checked": min(len(symbols), max_symbols),
        "by_source": {
            "edgar": {"fetched": total_fetched, "saved": saved, "duplicate": duplicate, "failed": failed},
            "news_us": {"fetched": news_fetched, "saved": news_saved, "duplicate": news_duplicate},
        },
    }


def collect_all_materials_daily() -> Dict:
    """日次総合収集"""
    jp = collect_jp_materials()
    us = collect_us_materials(max_symbols=20)
    return {"status": "ok", "jp": jp, "us": us}
