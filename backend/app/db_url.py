"""DATABASE_URL 正規化 + 秘密情報マスク表示ヘルパー

秘密(password / URL全文)は絶対に表示しない。
表示可: scheme / host / port / database / sslmode有無 / has_password
"""
import os
from typing import Dict, Optional, Tuple
from urllib.parse import urlsplit, urlunsplit, parse_qs, urlencode


def _backend_root() -> str:
    """backend/ ディレクトリの絶対パス (このファイルは backend/app/db_url.py)"""
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_database_url_from_file(path: str) -> Optional[str]:
    """env形式ファイルから DATABASE_URL= の値だけ読む (python-dotenv非依存)。
    秘密は返すが print はしない。見つからなければ None。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("export "):
                    line = line[len("export "):].strip()
                if line.startswith("DATABASE_URL="):
                    val = line[len("DATABASE_URL="):].strip()
                    # クオート除去
                    if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                        val = val[1:-1]
                    return val or None
    except FileNotFoundError:
        return None
    except Exception:
        return None
    return None


def _resolve_database_url() -> Tuple[str, str, Optional[str]]:
    """DATABASE_URL を優先順位で解決し (url, source, file_path) を返す。

    優先順位:
      1. 環境変数 DATABASE_URL
      2. LOCAL_TRAINING_ENV_FILE で指定されたファイル
      3. backend/.env.local-training
      4. backend/.env
      5. SQLite フォールバック (sqlite:///./screener.db)

    file_path は値の取得元ファイル (環境変数/フォールバック時は None)。
    """
    root = _backend_root()

    # 1. 環境変数
    env_val = os.getenv("DATABASE_URL")
    if env_val:
        return normalize_database_url(env_val), "env:DATABASE_URL", None

    # 2. LOCAL_TRAINING_ENV_FILE
    custom = os.getenv("LOCAL_TRAINING_ENV_FILE")
    if custom:
        path = custom if os.path.isabs(custom) else os.path.join(root, custom)
        val = _read_database_url_from_file(path)
        if val:
            return normalize_database_url(val), f"file:{os.path.basename(path)}", path

    # 3. backend/.env.local-training
    lt_path = os.path.join(root, ".env.local-training")
    val = _read_database_url_from_file(lt_path)
    if val:
        return normalize_database_url(val), "file:.env.local-training", lt_path

    # 4. backend/.env
    env_path = os.path.join(root, ".env")
    val = _read_database_url_from_file(env_path)
    if val:
        return normalize_database_url(val), "file:.env", env_path

    # 5. SQLite フォールバック
    return "sqlite:///./screener.db", "fallback:sqlite", None


def load_database_url_with_source() -> Tuple[str, str]:
    """DATABASE_URL を優先順位に従って解決し、(url, source) を返す。

    返す url は normalize 済み。source は人間可読なラベル (秘密を含まない)。
    優先順位の詳細は _resolve_database_url を参照。
    """
    url, source, _path = _resolve_database_url()
    return url, source


def _iter_env_file_pairs(path: str):
    """env形式ファイルから KEY=VALUE を順に yield する (秘密はprintしない)。"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if not s or s.startswith("#") or "=" not in s:
                    continue
                if s.startswith("export "):
                    s = s[len("export "):].strip()
                key, _, val = s.partition("=")
                key = key.strip()
                val = val.strip()
                if len(val) >= 2 and val[0] == val[-1] and val[0] in ("'", '"'):
                    val = val[1:-1]
                if key:
                    yield key, val
    except FileNotFoundError:
        return
    except Exception:
        return


def bootstrap_local_training_env() -> Tuple[str, str]:
    """ローカルCLI起動時の環境ブートストラップ。

    - DATABASE_URL を優先順位で解決し os.environ['DATABASE_URL'] に確定設定する
      (app.database が import 時に同じ値を使うようにするため)。
    - 解決元ファイルがあれば、その他のキー (CRON_SECRET / BACKEND_URL 等) を
      既存値を上書きせずに os.environ へ読み込む。
    - 秘密情報 (値) は一切 print しない。

    必ず app.database を import する前に呼ぶこと。戻り値は (url, source)。
    """
    url, source, path = _resolve_database_url()
    # 解決元ファイルのキーを setdefault で読み込む (DATABASE_URL以外も)
    if path:
        for key, val in _iter_env_file_pairs(path):
            if key == "DATABASE_URL":
                continue  # 下で正規化済みを設定する
            os.environ.setdefault(key, val)
    # DATABASE_URL を確定 (env source の場合は既に存在)
    os.environ["DATABASE_URL"] = url
    return url, source


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
