#!/usr/bin/env python
"""本番DB接続を最小処理で確認する (秘密情報は表示しない)

使い方:
  python scripts/test_db_connection.py
  python scripts/test_db_connection.py --driver psycopg2
  python scripts/test_db_connection.py --driver sqlalchemy
  python scripts/test_db_connection.py --debug

表示するのは scheme/host/port/database/sslmode/has_password と 成功/失敗のみ。
DATABASE_URL全文・password は絶対に表示しない。
"""
import os
import sys
import argparse
import traceback

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from dotenv import load_dotenv
load_dotenv()

from app.db_url import normalize_database_url, safe_database_url_info, psycopg2_connect_kwargs


def _print_info(url: str):
    info = safe_database_url_info(url)
    print(f"[DB] scheme={info.get('scheme')} host={info.get('host')} "
          f"port={info.get('port')} database={info.get('database')} "
          f"sslmode={info.get('sslmode')} has_password={info.get('has_password')}")
    return info


def test_psycopg2(url: str, debug: bool) -> bool:
    import psycopg2
    from urllib.parse import urlsplit, parse_qs
    parts = urlsplit(url)
    kwargs = psycopg2_connect_kwargs()
    try:
        conn = psycopg2.connect(
            host=parts.hostname, port=parts.port or 5432,
            dbname=parts.path.lstrip("/"), user=parts.username,
            password=parts.password, **kwargs,
        )
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        cur.execute("SELECT current_database(), now()")
        dbname, now = cur.fetchone()
        cur.close(); conn.close()
        print(f"[psycopg2] DB接続OK  current_database={dbname} now={now}")
        return True
    except Exception as e:
        print(f"[psycopg2 ERROR] {type(e).__name__}: {str(e).strip().splitlines()[0] if str(e).strip() else e}")
        if debug:
            traceback.print_exc()
        return False


def test_sqlalchemy(url: str, debug: bool) -> bool:
    from sqlalchemy import create_engine, text
    try:
        engine = create_engine(
            url, pool_pre_ping=True, pool_recycle=60, pool_size=1,
            max_overflow=0, pool_timeout=10,
            connect_args=psycopg2_connect_kwargs() if url.startswith("postgresql") else {},
        )
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            if url.startswith("postgresql"):
                row = conn.execute(text("SELECT current_database(), now()")).fetchone()
                print(f"[sqlalchemy] DB接続OK  current_database={row[0]} now={row[1]}")
            else:
                print("[sqlalchemy] DB接続OK (sqlite)")
        engine.dispose()
        return True
    except Exception as e:
        print(f"[sqlalchemy ERROR] {type(e).__name__}: {str(e).strip().splitlines()[0] if str(e).strip() else e}")
        if debug:
            traceback.print_exc()
        return False


def _hint():
    print("""
[HINT] 接続できない場合の確認:
  - Render DB が resume(稼働)しているか (Free は idle で停止することがある)
  - Internal URL ではなく External Database URL を使っているか
  - sslmode=require が付いているか (本ツールは自動付与)
  - resume直後は SSL が安定するまで1〜2分待って再試行
  - Singapore regionは初回接続でSSL切断が起きやすい → 数回retry
""")


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--driver", choices=["psycopg2", "sqlalchemy", "both"], default="both")
    p.add_argument("--debug", action="store_true")
    p.add_argument("--retries", type=int, default=2)
    args = p.parse_args()

    raw = os.getenv("DATABASE_URL", "")
    if not raw:
        print("[DB ERROR] DATABASE_URL not set in environment / .env")
        sys.exit(2)
    url = normalize_database_url(raw)
    info = _print_info(url)

    if not info.get("is_postgresql"):
        print("[DB] PostgreSQLではありません (sqlite等)。External接続テストはスキップ。")
        ok = test_sqlalchemy(url, args.debug)
        sys.exit(0 if ok else 1)

    ok = False
    for attempt in range(1, args.retries + 1):
        if attempt > 1:
            print(f"[retry {attempt}/{args.retries}] ...")
        if args.driver in ("psycopg2", "both"):
            ok = test_psycopg2(url, args.debug) or ok
        if args.driver in ("sqlalchemy", "both"):
            ok = test_sqlalchemy(url, args.debug) or ok
        if ok:
            break
    if not ok:
        _hint()
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
