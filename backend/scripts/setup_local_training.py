#!/usr/bin/env python
"""ローカル直結CLIの対話セットアップ (本番PostgreSQL接続)

Render External Database URL を手作業で .env に書く負担をなくすための対話ツール。
入力されたURLを正規化し backend/.env.local-training に保存し、接続テストまで実行する。

セキュリティ:
  - URL全文 / password / CRON_SECRET は絶対に表示しない (scheme/host/port/db/sslmodeのみ)
  - .env.local-training は .gitignore 済みであることを確認し、git管理下なら中止
  - 秘密情報を git add / push しない

使い方:
  cd backend
  venv\\Scripts\\activate
  python scripts/setup_local_training.py

これは投資助言ではありません。分析・学習・検証目的です。
"""
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db_url import normalize_database_url, safe_database_url_info

BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(BACKEND_ROOT, ".env.local-training")
ENV_FILE_NAME = ".env.local-training"
BACKEND_URL_DEFAULT = "https://stock-screener-backend-2h6a.onrender.com"


def _print_header():
    print("=" * 60)
    print(" ローカル直結CLI セットアップ (本番PostgreSQL)")
    print("=" * 60)
    print("""
Render Dashboard で接続URLを取得してください:
  1. https://dashboard.render.com を開く
  2. 対象の PostgreSQL を選択
  3. [Connections] → "External Database URL" をコピー
     (Internal ではなく External。postgres:// で始まる文字列)

貼り付けたURLは画面に表示されません (scheme/host等のみ表示)。
""")


def _ensure_gitignore():
    """ルート .gitignore に .env / .env.* / !.env.example があることを保証"""
    # backend のひとつ上がリポジトリルートと仮定
    repo_root = os.path.dirname(BACKEND_ROOT)
    gi_path = os.path.join(repo_root, ".gitignore")
    needed = [".env", ".env.*", "!.env.example"]
    try:
        existing = ""
        if os.path.exists(gi_path):
            with open(gi_path, "r", encoding="utf-8") as f:
                existing = f.read()
        lines = {ln.strip() for ln in existing.splitlines()}
        missing = [p for p in needed if p not in lines]
        if missing:
            with open(gi_path, "a", encoding="utf-8") as f:
                if existing and not existing.endswith("\n"):
                    f.write("\n")
                f.write("\n# local training secrets\n")
                for p in missing:
                    f.write(p + "\n")
            print(f"[gitignore] 追記: {', '.join(missing)}")
        else:
            print("[gitignore] OK (.env / .env.* / !.env.example 済み)")
    except Exception as e:
        print(f"[gitignore WARN] 確認に失敗: {e}")


def _git_tracked(path: str) -> bool:
    """path が git 管理下 (tracked) なら True"""
    try:
        r = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=BACKEND_ROOT, capture_output=True, text=True,
        )
        return r.returncode == 0
    except Exception:
        return False


def _read_url_interactive() -> str:
    try:
        url = input("External Database URL を貼り付けてください: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n[中止] 入力がキャンセルされました。")
        sys.exit(1)
    if not url:
        print("[ERROR] 空のため中止します。")
        sys.exit(1)
    if not (url.startswith("postgres://") or url.startswith("postgresql://")):
        print("[ERROR] postgres:// または postgresql:// で始まる必要があります。")
        print("        (Internal ではなく External Database URL を貼ってください)")
        sys.exit(1)
    return normalize_database_url(url)


def _save_env_file(url: str, cron_secret: str = ""):
    lines = [
        "# ローカル直結CLI 専用設定 (git管理しない / 秘密情報)",
        "# scripts/setup_local_training.py が生成。手で編集してもよい。",
        f"DATABASE_URL={url}",
        "LOCAL_TRAINING_CLI=true",
        f"BACKEND_URL={BACKEND_URL_DEFAULT}",
    ]
    if cron_secret:
        lines.append(f"CRON_SECRET={cron_secret}")
    with open(ENV_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"[保存] {ENV_FILE_NAME} を書き込みました (内容は表示しません)。")


def _run(cmd: list, env_extra: dict = None) -> int:
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    print(f"\n$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=BACKEND_ROOT, env=env).returncode


def main():
    _print_header()

    # 1. URL入力 & 正規化
    url = _read_url_interactive()
    info = safe_database_url_info(url)
    print(f"[DB] scheme={info.get('scheme')} host={info.get('host')} "
          f"port={info.get('port')} database={info.get('database')} "
          f"sslmode={info.get('sslmode')} has_password={info.get('has_password')}")

    # 2. CRON_SECRET (任意, APIフォールバック用)
    try:
        cron = input("CRON_SECRET (任意・未使用ならEnterでスキップ): ").strip()
    except (EOFError, KeyboardInterrupt):
        cron = ""

    # 3. .gitignore 保証
    _ensure_gitignore()

    # 4. 保存
    _save_env_file(url, cron)

    # 5. git 管理下でないことを確認
    if _git_tracked(ENV_FILE_NAME) or _git_tracked(os.path.join("backend", ENV_FILE_NAME)):
        print(f"[CRITICAL] {ENV_FILE_NAME} が git 管理下にあります！秘密漏洩の恐れ。")
        print("  対処: git rm --cached backend/.env.local-training してから .gitignore を確認。")
        sys.exit(1)
    print(f"[git] OK ({ENV_FILE_NAME} は未追跡)")

    # 6. 接続テスト
    py = sys.executable
    env_extra = {"LOCAL_TRAINING_ENV_FILE": ENV_FILE_NAME}
    rc = _run([py, "scripts/test_db_connection.py", "--driver", "psycopg2", "--require-postgres"], env_extra)
    if rc != 0:
        print("\n[ERROR] DB接続テストに失敗しました。")
        print("  Render DBがresume済みか / External URLか / 1-2分待って再試行。")
        sys.exit(1)

    # 7. status
    rc = _run([py, "scripts/run_local_training.py", "status", "--no-init", "--require-postgres"], env_extra)

    # 8. 次のコマンド案内
    print("\n" + "=" * 60)
    print(" セットアップ完了。以降は以下で実行できます:")
    print("=" * 60)
    print(r"""
  set LOCAL_TRAINING_ENV_FILE=.env.local-training   (cmd)
  $env:LOCAL_TRAINING_ENV_FILE=".env.local-training" (PowerShell)

  python scripts/run_local_training.py candidates --market JP --max-symbols 50 --require-postgres
  python scripts/run_local_training.py auto-save --market JP --require-postgres
  python scripts/run_local_training.py review --require-postgres
  python scripts/run_local_training.py save-training --require-postgres
  python scripts/run_local_training.py full --market JP --max-symbols 50 --require-postgres
""")
    print("これは投資助言ではありません。分析・学習・検証目的です。")
    sys.exit(0 if rc == 0 else 1)


if __name__ == "__main__":
    main()
