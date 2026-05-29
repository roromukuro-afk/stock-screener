"""DB接続: SQLite (デフォルト) / PostgreSQL (本番) 両対応"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from app.db_url import normalize_database_url, load_database_url_with_source

# DATABASE_URL 解決は優先順位ローダーに一本化する (load_dotenv は使わない)。
# 優先順位: env > LOCAL_TRAINING_ENV_FILE > .env.local-training > .env > sqlite
# ローカルCLIは bootstrap_local_training_env() で import 前に os.environ を確定する。
# 本番(Render)は実際の環境変数 DATABASE_URL が #1 で解決される。
DATABASE_URL, _DB_URL_SOURCE = load_database_url_with_source()

is_sqlite = DATABASE_URL.startswith("sqlite")
# ローカルCLI判定: 軽量pool + SSL keepalives で External 接続を安定させる
_is_local_cli = os.getenv("LOCAL_TRAINING_CLI", "false").lower() == "true"

if is_sqlite:
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,
    )

    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()
else:
    # PostgreSQL SSL安定 connect_args (Render External でのSSL切断対策)
    _pg_connect_args = {
        "sslmode": "require",
        "connect_timeout": 10,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
    }
    if _is_local_cli:
        # ローカルCLI: 単一接続・短命・pre_pingで安定優先
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=60,
            pool_size=1,
            max_overflow=0,
            pool_timeout=10,
            connect_args=_pg_connect_args,
            echo=False,
        )
    else:
        # Render本番API: 並列吸収できるpool
        engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=300,
            pool_size=10,
            max_overflow=20,
            pool_timeout=60,
            connect_args=_pg_connect_args,
            echo=False,
        )

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """全テーブル作成 + 既存テーブルへの新カラム idempotent migration"""
    from app.models import models  # noqa
    Base.metadata.create_all(bind=engine)
    # 包括的 ensure_schema (モデル定義との差分を非破壊で吸収)
    try:
        ensure_schema()
    except Exception as e:
        print(f"[init_db] ensure_schema failed (continuing): {e}")
    # 旧 migration (後方互換 / 念のため)
    migrate_add_columns_if_missing()


def _short_err(e: Exception) -> str:
    s = str(e).strip().splitlines()
    return (s[0] if s else str(e))[:200]


def _column_default_clause(col, is_pg: bool) -> str:
    """col.default が単純スカラーなら DEFAULT 句を返す (既存行をNULLにしないため)。"""
    d = getattr(col, "default", None)
    if d is None or not getattr(d, "is_scalar", False):
        return ""
    val = d.arg
    # bool は int のサブクラスなので先に判定
    if isinstance(val, bool):
        if is_pg:
            return f" DEFAULT {'TRUE' if val else 'FALSE'}"
        return f" DEFAULT {1 if val else 0}"
    if isinstance(val, (int, float)):
        return f" DEFAULT {val}"
    if isinstance(val, str):
        safe = val.replace("'", "''")
        return f" DEFAULT '{safe}'"
    return ""


def ensure_schema() -> dict:
    """モデル定義に対して本番DBに不足しているテーブル/カラムを非破壊で追加する。

    - CREATE TABLE は create_all が担当 (既存テーブルは変更しない)。
    - 既存テーブルに不足しているカラムだけ ALTER TABLE ADD COLUMN する。
    - DROP / TRUNCATE / 型変更 は一切行わない (idempotent / 非破壊)。
    - 失敗したテーブル/カラムは errors に短く記録 (秘密情報は出さない)。
    SQLite / PostgreSQL 両対応。
    """
    from app.models import models  # noqa: F401
    from sqlalchemy import inspect, text

    summary = {
        "dialect": engine.dialect.name,
        "created_tables": [],
        "added_columns": [],
        "errors": [],
        "checked_tables": 0,
    }

    # 1. 不足テーブルを作成
    try:
        before = set(inspect(engine).get_table_names())
        Base.metadata.create_all(bind=engine)
        after = set(inspect(engine).get_table_names())
        summary["created_tables"] = sorted(after - before)
    except Exception as e:
        summary["errors"].append(f"create_all: {_short_err(e)}")
        return summary

    # 2. 既存テーブルの不足カラムを追加
    inspector = inspect(engine)
    dialect = engine.dialect
    is_pg = dialect.name == "postgresql"
    for table_name, table in Base.metadata.tables.items():
        try:
            db_cols = {c["name"] for c in inspector.get_columns(table_name)}
        except Exception as e:
            summary["errors"].append(f"{table_name}: inspect: {_short_err(e)}")
            continue
        summary["checked_tables"] += 1
        for col in table.columns:
            if col.name in db_cols:
                continue
            try:
                type_sql = col.type.compile(dialect=dialect)
            except Exception:
                type_sql = "VARCHAR"
            default_sql = _column_default_clause(col, is_pg)
            # 識別子はダブルクオートで保護 (予約語対策)。事前チェック済みなのでIF NOT EXISTS不要だが
            # PostgreSQLでは競合防止に IF NOT EXISTS を付与。
            if is_pg:
                ddl = f'ALTER TABLE "{table_name}" ADD COLUMN IF NOT EXISTS "{col.name}" {type_sql}{default_sql}'
            else:
                ddl = f'ALTER TABLE "{table_name}" ADD COLUMN "{col.name}" {type_sql}{default_sql}'
            try:
                with engine.connect() as conn:
                    conn.execute(text(ddl))
                    conn.commit()
                summary["added_columns"].append(f"{table_name}.{col.name}")
            except Exception as e:
                summary["errors"].append(f"{table_name}.{col.name}: {_short_err(e)}")
    return summary


def migrate_add_columns_if_missing():
    """既存DBに後付けカラムを追加 (idempotent / SQLite + PostgreSQL 両対応)"""
    from sqlalchemy import inspect, text

    # (table, column, sql_type, default) のリスト
    migrations = [
        ("prediction_logs", "prediction_type", "VARCHAR(64)", "'tomorrow_prediction'"),
        ("prediction_logs", "prediction_horizon", "VARCHAR(32)", "'next_day'"),
        ("prediction_logs", "target_return", "FLOAT", "20.0"),
        ("prediction_logs", "auto_trade_candidate", "BOOLEAN", "TRUE"),
        ("prediction_logs", "watch_only", "BOOLEAN", "FALSE"),
    ]

    try:
        inspector = inspect(engine)
        table_names = set(inspector.get_table_names())
    except Exception as e:
        print(f"[migration] inspector failed: {e}")
        return

    for table, col, sql_type, default in migrations:
        if table not in table_names:
            continue
        try:
            existing = {c["name"] for c in inspector.get_columns(table)}
        except Exception:
            continue
        if col in existing:
            continue
        # add column
        try:
            with engine.connect() as conn:
                # SQLiteは BOOLEAN DEFAULT TRUE/FALSE を受けるが念のため数値で
                if is_sqlite and "BOOLEAN" in sql_type:
                    default_sql = "1" if default.upper() == "TRUE" else "0"
                else:
                    default_sql = default
                sql = f"ALTER TABLE {table} ADD COLUMN {col} {sql_type} DEFAULT {default_sql}"
                conn.execute(text(sql))
                conn.commit()
                print(f"[migration] {table} ADD COLUMN {col} {sql_type} DEFAULT {default_sql}")
        except Exception as e:
            print(f"[migration] {table}.{col} failed: {e}")


def get_db_info() -> dict:
    return {
        "url_scheme": DATABASE_URL.split(":", 1)[0],
        "is_sqlite": is_sqlite,
        "is_postgresql": DATABASE_URL.startswith("postgresql"),
        "source": _DB_URL_SOURCE,
    }
