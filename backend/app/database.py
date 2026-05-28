"""DB接続: SQLite (デフォルト) / PostgreSQL (本番) 両対応"""
import os
from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./screener.db")

# Render等が postgres:// を提供する場合 SQLAlchemy 2.x は postgresql:// が必要
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

is_sqlite = DATABASE_URL.startswith("sqlite")

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
    # PostgreSQL: Render Freeの並列処理(thread多用)を吸収できるpool
    engine = create_engine(
        DATABASE_URL,
        pool_pre_ping=True,
        pool_recycle=300,
        pool_size=10,
        max_overflow=20,
        pool_timeout=60,
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
    migrate_add_columns_if_missing()


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
    }
