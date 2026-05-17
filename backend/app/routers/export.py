from fastapi import APIRouter
from fastapi.responses import Response
from app.services.screener import get_progress
from app.services.exporter import export_csv, export_excel
from datetime import datetime

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/csv")
def download_csv(classification: str = None):
    p = get_progress()
    results = p.get("results", [])
    if classification:
        results = [r for r in results if r.get("classification") == classification]
    exclusions = p.get("exclusions", [])

    csv_bytes = export_csv(results)
    filename = f"screening_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return Response(
        content=csv_bytes,
        media_type="text/csv; charset=utf-8-sig",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/excel")
def download_excel():
    p = get_progress()
    results = p.get("results", [])
    exclusions = p.get("exclusions", [])
    excel_bytes = export_excel(results, exclusions)
    filename = f"screening_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )


@router.get("/aar/csv")
def download_aar_csv():
    from app.services.exporter import generate_aar_text
    p = get_progress()
    results = p.get("results", [])
    candidates = [r for r in results if r.get("classification") in ["採用候補", "条件付き候補", "監視候補"]]

    lines = []
    for r in candidates:
        lines.append(generate_aar_text(r))
        lines.append("\n" + "="*60 + "\n")

    content = "\n".join(lines)
    filename = f"aar_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    return Response(
        content=content.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
