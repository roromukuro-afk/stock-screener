"""DATABASE_URL 正規化 + 秘密情報マスク表示ヘルパー

秘密(password / URL全文)は絶対に表示しない。
表示可: scheme / host / port / database / sslmode有無 / has_password
"""
from typing import Dict
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode


def normalize_database_url(url: str) -> str:
    """DATABASE_URL を安全に正規化。
    - postgres:// → postgresql://
    - postgresql の場合 sslmode=require が無ければ付与
    SQLite等はそのまま返す。
    """
    if not url:
        return url
    # scheme正規化
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]

    if not url.startswith("postgresql"):
        return url  # sqlite等はそのまま

    parts = urlsplit(url)
    query = parse_qs(parts.query)
    if "sslmode" not in query:
        query["sslmode"] = ["require"]
    new_query = urlencode({k: v[0] for k, v in query.items()})
    return urlunsplit((parts.scheme, parts.netloc, parts.path, new_query, parts.fragment))


def safe_database_url_info(url: str) -> Dict:
    """秘密を出さずに接続先情報を返す"""
    if not url:
        return {"scheme": None, "error": "DATABASE_URL not set"}
    try:
        parts = urlsplit(url)
        query = parse_qs(parts.query)
        db_name = parts.path.lstrip("/") if parts.path else None
        return {
            "scheme": parts.scheme,
            "host": parts.hostname,
            "port": parts.port,
            "database": db_name,
            "sslmode": (query.get("sslmode") or [None])[0],
            "has_password": bool(parts.password),
            "is_postgresql": parts.scheme.startswith("postgresql") if parts.scheme else False,
        }
    except Exception as e:
        return {"scheme": "parse_error", "error": str(e)}


def psycopg2_connect_kwargs() -> Dict:
    """psycopg2 直結用の安定設定 (SSL切断対策)"""
    return {
        "sslmode": "require",
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
