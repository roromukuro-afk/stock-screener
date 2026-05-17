"""除外リスト管理 API (DB永続化)"""
from fastapi import APIRouter, UploadFile, File, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import io
import re

from app.db_repo import (
    list_exclusion_entries, add_exclusion_entry, remove_exclusion_entry
)

router = APIRouter(prefix="/api/exclusions", tags=["exclusions"])


class ExclusionItem(BaseModel):
    symbol: str
    name: Optional[str] = ""
    market: Optional[str] = ""
    reason: Optional[str] = "手動登録"


@router.get("")
def get_exclusions():
    items = list_exclusion_entries()
    return {"exclusions": items, "total": len(items)}


@router.post("")
def add_exclusion(item: ExclusionItem):
    added = add_exclusion_entry(item.symbol, item.name or "", item.market or "", item.reason or "手動登録")
    items = list_exclusion_entries()
    return {
        "message": f"{item.symbol} を{'追加しました' if added else '(既に登録済み)'}",
        "exclusions": items,
        "added": added,
    }


@router.delete("/{symbol}")
def remove_exclusion(symbol: str):
    removed = remove_exclusion_entry(symbol)
    if not removed:
        raise HTTPException(status_code=404, detail=f"{symbol} は除外リストにありません")
    return {"message": f"{symbol} を除外リストから削除しました"}


@router.post("/upload")
async def upload_exclusions(file: UploadFile = File(...)):
    content = await file.read()
    filename = file.filename or ""
    candidates = []

    if filename.lower().endswith((".csv", ".txt")):
        text = content.decode("utf-8-sig", errors="ignore")
        lines = text.strip().split("\n")
        for line in lines:
            line = line.strip()
            jp_matches = re.findall(r'\b(\d{4})(\.T)?\b', line)
            for m in jp_matches:
                sym = m[0] + ".T"
                candidates.append({"symbol": sym, "name": "", "market": "JP", "reason": "ファイルアップロード"})
            us_matches = re.findall(r'\b([A-Z]{2,5})\b', line)
            for m in us_matches:
                if m not in ["JP", "US", "ADR", "ETF", "ID", "NA", "USD", "JPY", "CSV"]:
                    candidates.append({"symbol": m, "name": "", "market": "US", "reason": "ファイルアップロード"})
    elif filename.lower().endswith((".xlsx", ".xls")):
        import pandas as pd
        try:
            df = pd.read_excel(io.BytesIO(content), dtype=str)
            for col in df.columns:
                for val in df[col].dropna():
                    val = str(val).strip()
                    jp = re.match(r'^(\d{4})(\.T)?$', val)
                    if jp:
                        candidates.append({"symbol": jp.group(1) + ".T", "name": "", "market": "JP", "reason": "Excelアップロード"})
                    elif re.match(r'^[A-Z]{2,5}$', val):
                        candidates.append({"symbol": val, "name": "", "market": "US", "reason": "Excelアップロード"})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Excel読み込みエラー: {e}")
    elif filename.lower().endswith(".pdf"):
        try:
            text = content.decode("latin-1", errors="ignore")
            jp_matches = re.findall(r'\b(\d{4})(\.T)?\b', text)
            for m in jp_matches[:200]:
                sym = m[0] + ".T"
                candidates.append({"symbol": sym, "name": "", "market": "JP", "reason": "PDF抽出(要確認)"})
            us_matches = re.findall(r'\b([A-Z]{3,5})\b', text)
            for m in us_matches[:100]:
                candidates.append({"symbol": m, "name": "", "market": "US", "reason": "PDF抽出(要確認)"})
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"PDF読み込みエラー: {e}")

    seen = set()
    unique_candidates = []
    for c in candidates:
        if c["symbol"] not in seen:
            seen.add(c["symbol"])
            unique_candidates.append(c)

    return {
        "filename": filename,
        "candidates": unique_candidates,
        "count": len(unique_candidates),
        "message": f"{len(unique_candidates)}件の銘柄候補を抽出しました。確認後、登録してください。"
    }


@router.post("/bulk")
def bulk_add_exclusions(items: List[ExclusionItem]):
    added_list = []
    skipped_list = []
    for item in items:
        if add_exclusion_entry(item.symbol, item.name or "", item.market or "", item.reason or "ファイル登録"):
            added_list.append(item.symbol)
        else:
            skipped_list.append(item.symbol)
    final = list_exclusion_entries()
    return {
        "added": added_list,
        "skipped": skipped_list,
        "total_exclusions": len(final),
    }
