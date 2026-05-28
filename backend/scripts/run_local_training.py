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

from dotenv import load_dotenv
load_dotenv()


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


def main():
    p = argparse.ArgumentParser(description="ローカル surge-20 教師データ構築 (本番DB直結)")
    sub = p.add_subparsers(dest="command", required=True)

    def add_common(sp):
        sp.add_argument("--market", default="JP", choices=["JP", "US"])
        sp.add_argument("--max-symbols", type=int, default=50, dest="max_symbols")
        sp.add_argument("--chunk", type=int, default=15)
        sp.add_argument("--max-chunks", type=int, default=1, dest="max_chunks")
        sp.add_argument("--priority", default="known_surge_first")

    sp = sub.add_parser("status"); sp.set_defaults(func=cmd_status)
    sp = sub.add_parser("expand"); add_common(sp); sp.set_defaults(func=cmd_expand)
    sp = sub.add_parser("candidates"); add_common(sp); sp.set_defaults(func=cmd_candidates)
    sp = sub.add_parser("auto-save"); sp.add_argument("--market", default="JP"); sp.add_argument("--limit", type=int, default=20); sp.add_argument("--min-score", type=float, default=70.0, dest="min_score"); sp.set_defaults(func=cmd_auto_save)
    sp = sub.add_parser("review"); sp.add_argument("--limit", type=int, default=100); sp.set_defaults(func=cmd_review)
    sp = sub.add_parser("save-training"); sp.set_defaults(func=cmd_save_training)
    sp = sub.add_parser("cleanup"); sp.add_argument("--consolidate", action="store_true"); sp.set_defaults(func=cmd_cleanup)
    sp = sub.add_parser("full"); add_common(sp); sp.set_defaults(func=cmd_full)

    args = p.parse_args()
    # DB情報を最初に表示
    from app.database import get_db_info
    info = get_db_info()
    print(f"[DB] scheme={info.get('url_scheme')} postgresql={info.get('is_postgresql')}")
    # テーブル作成 (本番DBに無ければ作る)
    try:
        from app.database import init_db
        init_db()
    except Exception as e:
        print(f"[init_db warn] {e}")
    args.func(args)


if __name__ == "__main__":
    main()
