#!/usr/bin/env python
"""ローカルPCで重い surge-20 処理を実行し、結果を DATABASE_URL のDBに直接書き込む。

Render Free (512MB) では重い学習処理が OOM/タイムアウトするため、
重い処理はローカルPCで実行し、本番 PostgreSQL に直接蓄積する運用。

使い方:
  # backend/.env の DATABASE_URL を Render PostgreSQL の External URL にする
  #   DATABASE_URL=postgresql://USER:PASS@HOST.oregon-postgres.render.com/DBNAME
  # (または SQLite ローカルのまま試す場合は変更不要)

  cd backend
  venv\\Scripts\\activate
  python scripts/run_local_training.py status
  python scripts/run_local_training.py expand --market JP --max-symbols 50 --chunk 15
  python scripts/run_local_training.py candidates --market JP --max-symbols 50
  python scripts/run_local_training.py auto-save --market JP
  python scripts/run_local_training.py review
  python scripts/run_local_training.py save-training
  python scripts/run_local_training.py full --market JP --max-symbols 50

これは投資助言ではありません。分析・学習・検証目的です。
"""
import os
import sys
import argparse
import json

# backend ルートを import パスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# ローカルCLIモードを宣言 (database.py が軽量pool+SSL keepalivesを使う)
os.environ.setdefault("LOCAL_TRAINING_CLI", "true")

# 注意: load_dotenv() は使わない。
# DATABASE_URL は優先順位で解決する
# (env > LOCAL_TRAINING_ENV_FILE > .env.local-training > .env > sqlite)。
from app.db_url import safe_database_url_info, bootstrap_local_training_env

# app.database を import する前に os.environ['DATABASE_URL'] を確定し、
# 解決元ファイルの CRON_SECRET / BACKEND_URL も読み込む (秘密はprintしない)。
_BOOT_URL, _BOOT_SOURCE = bootstrap_local_training_env()

_SETUP_HINT = (
    "[HINT] 本番PostgreSQLに接続するには:  python scripts/setup_local_training.py"
    "  (または PowerShell: .\\scripts\\setup_local_training.ps1)"
)


def _db_ping(debug: bool = False) -> bool:
    """軽量DB ping (SELECT 1)。成功でTrue。失敗時は短いエラー。"""
    from sqlalchemy import text
    from app.database import engine
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        print("[DB] ping=ok")
        return True
    except Exception as e:
        msg = str(e).strip().splitlines()[0] if str(e).strip() else str(e)
        print(f"[DB ERROR] Could not connect to database.\n  reason: {msg}")
        print("  hint: Render DBがresume済みか / External URLか / sslmode=require / resume後1-2分待って再試行")
        if debug:
            import traceback; traceback.print_exc()
        return False


def _print_db_info():
    info = safe_database_url_info(_BOOT_URL)
    print(f"[ENV] source={_BOOT_SOURCE}")
    print(f"[DB] scheme={info.get('scheme')} host={info.get('host')} "
          f"port={info.get('port')} sslmode={info.get('sslmode')}")
    return info


def _print(label, obj):
    print(f"\n=== {label} ===")
    try:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    except Exception:
        print(obj)


def cmd_status(args):
    from app.services import surge_20
    from app.database import get_db_info
    _print("DB", get_db_info())
    _print("light-status", surge_20.get_light_status())
    _print("data-quality", surge_20.get_data_quality())


def cmd_ensure_schema(args):
    """DB直結で不足テーブル/カラムを非破壊追加。"""
    from app.database import ensure_schema
    _print("ensure_schema", ensure_schema())


def cmd_expand(args):
    from app.services.surge_20 import expand_training_chunked
    r = expand_training_chunked(
        market=args.market, chunk_size=args.chunk,
        max_chunks_per_run=args.max_chunks, priority_mode=args.priority,
    )
    _print("expand_training", r)


def cmd_candidates(args):
    from app.services.surge_20 import build_and_save_candidates
    r = build_and_save_candidates(market=args.market, max_symbols=args.max_symbols, min_similarity=0.4)
    _print("candidate_build", r)


def cmd_auto_save(args):
    from app.services.surge_20 import auto_save_top_candidates
    r = auto_save_top_candidates(market=args.market, limit=args.limit, min_score=args.min_score)
    _print("auto_save", r)


def cmd_review(args):
    from app.services.surge_20 import review_surge_20_predictions
    r = review_surge_20_predictions(limit=args.limit)
    _print("review", r)


def cmd_save_training(args):
    from app.services.surge_20 import save_surge_20_reviews_as_training
    r = save_surge_20_reviews_as_training()
    _print("save_training", r)


def cmd_cleanup(args):
    from app.services.surge_20 import cleanup_orphan_pre_features, consolidate_duplicate_events
    _print("orphan_cleanup", cleanup_orphan_pre_features())
    if args.consolidate:
        _print("consolidate", consolidate_duplicate_events(min_gap_days=5))


def cmd_full(args):
    """ローカルで full フロー: expand → candidates → auto-save → review → save-training"""
    from app.services.surge_20 import (
        cleanup_orphan_pre_features, expand_training_chunked,
        build_and_save_candidates, auto_save_top_candidates,
        review_surge_20_predictions, save_surge_20_reviews_as_training,
        get_data_quality,
    )
    _print("orphan_cleanup", cleanup_orphan_pre_features())
    _print("expand", expand_training_chunked(
        market=args.market, chunk_size=args.chunk,
        max_chunks_per_run=args.max_chunks, priority_mode=args.priority))
    _print("candidates", build_and_save_candidates(
        market=args.market, max_symbols=args.max_symbols, min_similarity=0.4))
    _print("auto_save", auto_save_top_candidates(market=args.market, limit=20, min_score=70.0))
    _print("review", review_surge_20_predictions(limit=50))
    _print("save_training", save_surge_20_reviews_as_training())
    _print("data_quality", get_data_quality())


# ===== API mode (DB直結が不安定な場合のフォールバック) =====
def _api_call(method: str, path: str, body: dict = None, debug: bool = False):
    import requests
    backend = os.getenv("BACKEND_URL", "https://stock-screener-backend-2h6a.onrender.com")
    secret = os.getenv("CRON_SECRET", "")
    headers = {"Content-Type": "application/json"}
    if secret and path.startswith("/api/automation"):
        headers["X-Cron-Secret"] = secret
    try:
        if method == "GET":
            r = requests.get(f"{backend}{path}", headers=headers, timeout=120)
        else:
            r = requests.post(f"{backend}{path}", headers=headers, json=body or {}, timeout=120)
        print(f"[API {method} {path}] HTTP {r.status_code}")
        try:
            return r.json()
        except Exception:
            return {"raw": r.text[:300]}
    except Exception as e:
        msg = str(e).strip().splitlines()[0] if str(e).strip() else str(e)
        print(f"[API ERROR] {msg}")
        return {"error": msg}


def cmd_api_status(args):
    """複数の確認APIを順番に叩く。1つ失敗しても他を表示する。"""
    endpoints = [
        ("health", "GET", "/api/health"),
        ("automation-status", "GET", "/api/automation/status"),
        ("light-status", "GET", "/api/surge-20/light-status"),
        ("automation-jobs", "GET", "/api/automation/jobs?limit=5"),
        ("automation-errors", "GET", "/api/automation/errors?limit=5"),
    ]
    for label, method, path in endpoints:
        _print(label, _api_call(method, path))


def cmd_api_ensure_schema(args):
    """本番DBの不足テーブル/カラムを非破壊で追加 (CRON_SECRET必須)。"""
    _print("ensure-schema", _api_call("POST", "/api/automation/ensure-schema", {}))


def cmd_api_candidates(args):
    _print("candidate-build", _api_call("POST", "/api/automation/run-surge-20-candidate-build",
                                        {"market": args.market, "max_symbols": args.max_symbols}))


def cmd_api_auto_save(args):
    _print("auto-save", _api_call("POST", "/api/automation/auto-save-surge-20-predictions",
                                  {"market": args.market}))


def cmd_api_review(args):
    _print("review", _api_call("POST", "/api/automation/review-surge-20-predictions", {}))


def cmd_api_save_training(args):
    _print("save-training", _api_call("POST", "/api/automation/save-surge-20-reviews-as-training", {}))


_API_DISPATCH = {
    "status": cmd_api_status, "candidates": cmd_api_candidates,
    "auto-save": cmd_api_auto_save, "review": cmd_api_review,
    "save-training": cmd_api_save_training,
    "ensure-schema": cmd_api_ensure_schema,
}


def main():
    # 共通オプションを全subcommandに付ける parent parser
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--no-init", action="store_true", help="init_db()/create_allをスキップ")
    common.add_argument("--debug", action="store_true", help="失敗時にtracebackを表示")
    common.add_argument("--mode", choices=["db", "api", "auto"], default="db",
                        help="db=DB直結 / api=Render API経由 / auto=db失敗時にapi")
    common.add_argument("--require-postgres", action="store_true", dest="require_postgres",
                        help="SQLiteフォールバック時は処理を拒否 (本番DB接続を強制)")

    p = argparse.ArgumentParser(
        description="ローカル surge-20 教師データ構築 (本番DB直結 / APIフォールバック)",
        parents=[common],
    )
    sub = p.add_subparsers(dest="command", required=True)

    def add_full(sp):
        sp.add_argument("--market", default="JP", choices=["JP", "US"])
        sp.add_argument("--max-symbols", type=int, default=50, dest="max_symbols")
        sp.add_argument("--chunk", type=int, default=15)
        sp.add_argument("--max-chunks", type=int, default=1, dest="max_chunks")
        sp.add_argument("--priority", default="known_surge_first")

    sp = sub.add_parser("status", parents=[common]); sp.set_defaults(func=cmd_status)
    sp = sub.add_parser("ensure-schema", parents=[common]); sp.set_defaults(func=cmd_ensure_schema)
    sp = sub.add_parser("expand", parents=[common]); add_full(sp); sp.set_defaults(func=cmd_expand)
    sp = sub.add_parser("candidates", parents=[common]); add_full(sp); sp.set_defaults(func=cmd_candidates)
    sp = sub.add_parser("auto-save", parents=[common]); sp.add_argument("--market", default="JP"); sp.add_argument("--max-symbols", type=int, default=50, dest="max_symbols"); sp.add_argument("--limit", type=int, default=20); sp.add_argument("--min-score", type=float, default=70.0, dest="min_score"); sp.set_defaults(func=cmd_auto_save)
    sp = sub.add_parser("review", parents=[common]); sp.add_argument("--limit", type=int, default=100); sp.set_defaults(func=cmd_review)
    sp = sub.add_parser("save-training", parents=[common]); sp.set_defaults(func=cmd_save_training)
    sp = sub.add_parser("cleanup", parents=[common]); sp.add_argument("--consolidate", action="store_true"); sp.set_defaults(func=cmd_cleanup)
    sp = sub.add_parser("full", parents=[common]); add_full(sp); sp.set_defaults(func=cmd_full)

    args = p.parse_args()
    info = _print_db_info()

    # ---- require-postgres ガード (API modeは対象外) ----
    if getattr(args, "require_postgres", False) and args.mode != "api":
        if not info.get("is_postgresql"):
            print("[DB ERROR] DATABASE_URL が PostgreSQL ではありません (SQLiteフォールバック)。")
            print("  --require-postgres 指定時は本番DB接続が必須です。処理を中止します。")
            print(_SETUP_HINT)
            sys.exit(1)

    # ---- API mode ----
    if args.mode == "api":
        fn = _API_DISPATCH.get(args.command)
        if not fn:
            print(f"[API mode] '{args.command}' はAPIモード未対応。status/candidates/auto-save/review/save-training のみ。")
            sys.exit(2)
        fn(args)
        return

    # ---- DB mode (default) ----
    if not _db_ping(debug=args.debug):
        if args.mode == "auto":
            print("[mode=auto] DB接続失敗 → APIモードにフォールバック")
            fn = _API_DISPATCH.get(args.command)
            if fn:
                fn(args)
                return
        sys.exit(1)

    if not args.no_init:
        try:
            from app.database import init_db
            init_db()
        except Exception as e:
            print(f"[init_db warn] {str(e).strip().splitlines()[0] if str(e).strip() else e}")

    args.func(args)


if __name__ == "__main__":
    main()
