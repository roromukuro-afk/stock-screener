"""銘柄ユニバース取得・分類サービス

JPX / NasdaqTrader.com から実データを取得し、ETF/Warrant/Unit/Right/Preferred/Test Issue/ADR/普通株 を分類する
"""
import io
import re
import hashlib
import logging
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import requests
import pandas as pd

logger = logging.getLogger(__name__)

JPX_URL = "https://www.jpx.co.jp/markets/statistics-equities/misc/tvdivq0000001vg2-att/data_j.xls"
NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/nasdaqlisted.txt"
OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/symdir/otherlisted.txt"

REQ_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; StockScreener/1.0)"}

# ===== 米国銘柄: Security Name から分類 =====
ADR_PATTERNS = [
    r"American Depositary Shares",
    r"American Depositary Share",
    r"American Depository Shares",
    r"American Depository Share",
    r"\bADS\b",
    r"\bADR\b",
    r"Depositary Shares",
]
WARRANT_PATTERNS = [r"\bWarrants?\b", r"\bWts\b", r"to purchase"]
UNIT_PATTERNS = [r"\bUnits?\b"]
RIGHT_PATTERNS = [r"\bRights?\b"]
PREFERRED_PATTERNS = [
    r"\bPreferred\b", r"\bPreference\b", r"% Series",
    r"Depositary Shares each representing", r"% Cumulative",
    r"Pfd", r"Cumulative Redeemable",
]
FUND_PATTERNS = [r"\bClosed End Fund\b", r"\bFund\b", r"\bTrust\b"]
ETN_PATTERNS = [r"\bETN\b", r"Exchange[- ]Traded Note", r"Exchange[- ]Traded Notes"]
NOTE_PATTERNS = [r"\bNotes? due\b", r"Senior Notes?\b"]
BOND_PATTERNS = [r"\bBonds?\b"]
SPAC_PATTERNS = [r"Acquisition Corp", r"Acquisition Corporation"]
COMMON_PATTERNS = [
    r"Common Stock", r"Common Shares",
    r"Ordinary Shares", r"Class [A-Z] Common Stock",
    r"Class [A-Z] Common Shares", r"Class [A-Z] Ordinary Shares",
]


def _matches_any(text: str, patterns) -> bool:
    if not text:
        return False
    for p in patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def classify_us_security(security_name: str, is_etf_flag: bool = False, is_test_flag: bool = False) -> Dict:
    """米国銘柄のSecurity Nameを分類"""
    name = security_name or ""

    is_etf = bool(is_etf_flag) or _matches_any(name, [r"\bETF\b"]) or _matches_any(name, ETN_PATTERNS)
    is_test = bool(is_test_flag)
    is_warrant = _matches_any(name, WARRANT_PATTERNS)
    is_unit = _matches_any(name, UNIT_PATTERNS)
    is_right = _matches_any(name, RIGHT_PATTERNS)
    is_preferred = _matches_any(name, PREFERRED_PATTERNS)
    is_note = _matches_any(name, NOTE_PATTERNS) or _matches_any(name, BOND_PATTERNS)
    is_fund = _matches_any(name, FUND_PATTERNS) and not _matches_any(name, COMMON_PATTERNS)
    is_adr = _matches_any(name, ADR_PATTERNS)
    is_spac = _matches_any(name, SPAC_PATTERNS) and (is_warrant or is_unit or is_right)
    is_common = _matches_any(name, COMMON_PATTERNS)

    # 優先順位: test > warrant/unit/right > preferred > note/bond > etf/etn > fund > adr > common
    if is_test:
        instrument_type = "test_issue"
    elif is_warrant:
        instrument_type = "warrant"
    elif is_unit:
        instrument_type = "unit"
    elif is_right:
        instrument_type = "right"
    elif is_preferred:
        instrument_type = "preferred"
    elif is_note:
        instrument_type = "note"
    elif is_etf:
        instrument_type = "etf"
    elif is_fund:
        instrument_type = "fund"
    elif is_adr:
        instrument_type = "adr"
    elif is_common:
        instrument_type = "common_stock"
    else:
        # 補助的に「Common Stock」が無くても他に該当なし → common_stock 推定
        instrument_type = "common_stock"

    is_common_stock = instrument_type == "common_stock"
    is_screening_eligible = instrument_type in ("common_stock", "adr") and not (is_test or is_warrant or is_unit or is_right)

    exclusion_reason = None
    if not is_screening_eligible:
        exclusion_reason = f"instrument_type:{instrument_type}"

    return {
        "instrument_type": instrument_type,
        "is_common_stock": is_common_stock,
        "is_adr": is_adr,
        "is_etf": is_etf,
        "is_warrant": is_warrant,
        "is_unit": is_unit,
        "is_right": is_right,
        "is_preferred": is_preferred,
        "is_spac": is_spac,
        "is_fund": is_fund,
        "is_test_issue": is_test,
        "is_screening_eligible": is_screening_eligible,
        "exclusion_reason": exclusion_reason,
    }


# ===== JPX =====
def fetch_jpx() -> Tuple[List[Dict], Dict]:
    """JPX上場銘柄一覧Excelを取得"""
    meta = {"source_url": JPX_URL, "fetched_at": datetime.utcnow().isoformat()}
    try:
        r = requests.get(JPX_URL, headers=REQ_HEADERS, timeout=30)
        r.raise_for_status()
        meta["checksum"] = hashlib.md5(r.content).hexdigest()
        meta["row_count_raw"] = 0

        df = pd.read_excel(io.BytesIO(r.content), dtype=str)
        df.columns = df.columns.str.strip()

        # JPX標準カラム: 日付,コード,銘柄名,市場・商品区分,33業種コード,33業種区分,17業種コード,17業種区分,規模コード,規模区分
        col_code = next((c for c in df.columns if "コード" in c), None)
        col_name = next((c for c in df.columns if "銘柄名" in c), None)
        col_market = next((c for c in df.columns if "市場" in c or "区分" in c), None)
        col_sector = next((c for c in df.columns if "33業種区分" in c), None)

        if not col_code or not col_name:
            meta["status"] = "failed"
            meta["error"] = f"required columns missing: {df.columns.tolist()}"
            return [], meta

        items = []
        for _, row in df.iterrows():
            code = str(row.get(col_code, "")).strip()
            if not code or not re.match(r"^\d{4,5}[A-Z0-9]?$", code):
                continue
            name = str(row.get(col_name, "")).strip()
            market_seg = str(row.get(col_market, "")).strip() if col_market else ""
            sector = str(row.get(col_sector, "")).strip() if col_sector else ""

            # ETF/REIT/出資証券などはJPXの市場区分から判定
            is_etf = "ETF" in market_seg or "ETN" in market_seg
            is_reit = "REIT" in market_seg or "投資" in market_seg
            is_test = False

            if is_etf:
                instrument_type = "etf"
                is_common = False
                eligible = False
                exclusion = "instrument_type:etf"
            elif is_reit:
                instrument_type = "fund"
                is_common = False
                eligible = False
                exclusion = "instrument_type:fund"
            else:
                instrument_type = "common_stock"
                is_common = True
                eligible = True
                exclusion = None

            items.append({
                "raw_symbol": code,
                "symbol": f"{code}.T",
                "yahoo_symbol": f"{code}.T",
                "name": name,
                "market": "JP",
                "exchange": market_seg or "TSE",
                "source": "JPX",
                "country": "Japan",
                "currency": "JPY",
                "instrument_type": instrument_type,
                "is_common_stock": is_common,
                "is_adr": False,
                "is_etf": is_etf,
                "is_warrant": False,
                "is_unit": False,
                "is_right": False,
                "is_preferred": False,
                "is_spac": False,
                "is_fund": is_reit,
                "is_test_issue": is_test,
                "is_screening_eligible": eligible,
                "exclusion_reason": exclusion,
                "sector": sector,
            })

        meta["status"] = "ok"
        meta["row_count"] = len(items)
        meta["file_name"] = "data_j.xls"
        return items, meta
    except Exception as e:
        logger.exception("JPX fetch failed")
        meta["status"] = "failed"
        meta["error"] = str(e)
        return [], meta


# ===== Nasdaq listed =====
def _parse_pipe_file(text: str) -> Tuple[List[Dict], Optional[str]]:
    """NasdaqTraderのパイプ区切りファイルをパース。最後の "File Creation Time" 行は除外"""
    lines = text.strip().split("\n")
    if len(lines) < 2:
        return [], None
    header = [c.strip() for c in lines[0].split("|")]
    rows = []
    file_creation_time = None
    for line in lines[1:]:
        if line.startswith("File Creation Time"):
            file_creation_time = line.replace("File Creation Time:", "").strip().split("|")[0].strip()
            continue
        parts = line.split("|")
        if len(parts) < len(header):
            continue
        row = {header[i]: parts[i].strip() for i in range(len(header))}
        rows.append(row)
    return rows, file_creation_time


def fetch_nasdaq_listed() -> Tuple[List[Dict], Dict]:
    """nasdaqlisted.txt を取得"""
    meta = {"source_url": NASDAQ_LISTED_URL, "fetched_at": datetime.utcnow().isoformat()}
    try:
        r = requests.get(NASDAQ_LISTED_URL, headers=REQ_HEADERS, timeout=30)
        r.raise_for_status()
        meta["checksum"] = hashlib.md5(r.content).hexdigest()
        text = r.text
        rows, file_ct = _parse_pipe_file(text)
        meta["file_creation_time"] = file_ct
        meta["file_name"] = "nasdaqlisted.txt"

        items = []
        for row in rows:
            symbol = row.get("Symbol", "").strip()
            if not symbol:
                continue
            sec_name = row.get("Security Name", "")
            is_etf_flag = row.get("ETF", "N") == "Y"
            is_test_flag = row.get("Test Issue", "N") == "Y"
            market_cat = row.get("Market Category", "")
            financial_status = row.get("Financial Status", "")

            cls = classify_us_security(sec_name, is_etf_flag, is_test_flag)

            items.append({
                "raw_symbol": symbol,
                "symbol": symbol,
                "yahoo_symbol": symbol,
                "name": sec_name,
                "market": "US",
                "exchange": "NASDAQ",
                "source": "nasdaqlisted",
                "country": "United States",
                "currency": "USD",
                "market_category": market_cat,
                "financial_status": financial_status,
                **cls,
            })

        meta["status"] = "ok"
        meta["row_count"] = len(items)
        return items, meta
    except Exception as e:
        logger.exception("nasdaqlisted fetch failed")
        meta["status"] = "failed"
        meta["error"] = str(e)
        return [], meta


def fetch_other_listed() -> Tuple[List[Dict], Dict]:
    """otherlisted.txt (NYSE / NYSE American / NYSE Arca / BATS / IEX) を取得"""
    meta = {"source_url": OTHER_LISTED_URL, "fetched_at": datetime.utcnow().isoformat()}
    try:
        r = requests.get(OTHER_LISTED_URL, headers=REQ_HEADERS, timeout=30)
        r.raise_for_status()
        meta["checksum"] = hashlib.md5(r.content).hexdigest()
        text = r.text
        rows, file_ct = _parse_pipe_file(text)
        meta["file_creation_time"] = file_ct
        meta["file_name"] = "otherlisted.txt"

        items = []
        for row in rows:
            # otherlisted.txt: ACT Symbol|Security Name|Exchange|CQS Symbol|ETF|Round Lot Size|Test Issue|NASDAQ Symbol
            symbol = row.get("ACT Symbol", "").strip() or row.get("NASDAQ Symbol", "").strip()
            if not symbol:
                continue
            sec_name = row.get("Security Name", "")
            is_etf_flag = row.get("ETF", "N") == "Y"
            is_test_flag = row.get("Test Issue", "N") == "Y"
            exchange_code = row.get("Exchange", "")
            exchange_map = {
                "N": "NYSE",
                "A": "NYSE American",
                "P": "NYSE Arca",
                "Z": "BATS",
                "V": "IEX",
                "Q": "NASDAQ",
            }
            exchange = exchange_map.get(exchange_code, exchange_code or "OTHER")

            cls = classify_us_security(sec_name, is_etf_flag, is_test_flag)

            items.append({
                "raw_symbol": symbol,
                "symbol": symbol,
                "yahoo_symbol": symbol,
                "name": sec_name,
                "market": "US",
                "exchange": exchange,
                "source": "otherlisted",
                "country": "United States",
                "currency": "USD",
                **cls,
            })

        meta["status"] = "ok"
        meta["row_count"] = len(items)
        return items, meta
    except Exception as e:
        logger.exception("otherlisted fetch failed")
        meta["status"] = "failed"
        meta["error"] = str(e)
        return [], meta


def merge_universe(*item_lists) -> List[Dict]:
    """複数ソースをマージ、重複は最初に出現したものを優先"""
    seen = set()
    merged = []
    for items in item_lists:
        for item in items:
            key = item["symbol"]
            if key in seen:
                continue
            seen.add(key)
            item["duplicate_key"] = key
            merged.append(item)
    return merged


def get_summary_counts(items: List[Dict]) -> Dict:
    """ユニバースの統計"""
    counts = {
        "total": len(items),
        "by_market": {},
        "by_source": {},
        "by_instrument_type": {},
        "eligible_count": 0,
        "common_stock_count": 0,
        "adr_count": 0,
        "etf_count": 0,
        "warrant_count": 0,
        "unit_count": 0,
        "right_count": 0,
        "preferred_count": 0,
        "test_issue_count": 0,
        "fund_count": 0,
    }
    for it in items:
        m = it.get("market", "?")
        counts["by_market"][m] = counts["by_market"].get(m, 0) + 1
        s = it.get("source", "?")
        counts["by_source"][s] = counts["by_source"].get(s, 0) + 1
        t = it.get("instrument_type", "?")
        counts["by_instrument_type"][t] = counts["by_instrument_type"].get(t, 0) + 1
        if it.get("is_screening_eligible"):
            counts["eligible_count"] += 1
        if it.get("is_common_stock"):
            counts["common_stock_count"] += 1
        if it.get("is_adr"):
            counts["adr_count"] += 1
        if it.get("is_etf"):
            counts["etf_count"] += 1
        if it.get("is_warrant"):
            counts["warrant_count"] += 1
        if it.get("is_unit"):
            counts["unit_count"] += 1
        if it.get("is_right"):
            counts["right_count"] += 1
        if it.get("is_preferred"):
            counts["preferred_count"] += 1
        if it.get("is_test_issue"):
            counts["test_issue_count"] += 1
        if it.get("is_fund"):
            counts["fund_count"] += 1
    return counts
