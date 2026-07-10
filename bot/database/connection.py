from contextlib import contextmanager
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from config import settings
from database.models import Base

logger = logging.getLogger("hypertech.db")

IS_SQLITE = settings.DATABASE_URL.startswith("sqlite")
engine_kwargs = {"echo": settings.DEBUG}

if IS_SQLITE:
    engine_kwargs["connect_args"] = {"check_same_thread": False}
else:
    engine_kwargs.update(
        {
            "pool_size": 10,
            "max_overflow": 20,
            "pool_pre_ping": True,
        }
    )

engine = create_engine(settings.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, expire_on_commit=False, bind=engine)
BOT_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI_PATH = BOT_ROOT / "alembic.ini"
ALEMBIC_SCRIPT_PATH = BOT_ROOT / "alembic"


def _get_alembic_config() -> Config:
    alembic_cfg = Config(str(ALEMBIC_INI_PATH))
    alembic_cfg.set_main_option("script_location", str(ALEMBIC_SCRIPT_PATH))
    alembic_cfg.set_main_option("sqlalchemy.url", settings.DATABASE_URL)
    return alembic_cfg



def _bootstrap_missing_tables() -> None:
    for table in Base.metadata.sorted_tables:
        table.create(bind=engine, checkfirst=True)



def _repair_legacy_schema() -> None:
    """Add columns missing from older schema versions.

    SQLite does not support ``ADD COLUMN IF NOT EXISTS``, so we check
    the inspector first and only add what's missing.
    """
    with engine.begin() as connection:
        inspector = inspect(connection)
        if "downloads" not in inspector.get_table_names():
            return

        existing_columns = {col["name"] for col in inspector.get_columns("downloads")}
        dialect = connection.dialect.name

        additions = [
            ("chat_id", "BIGINT"),
            ("request_message_id", "INTEGER"),
            ("status_message_id", "INTEGER"),
        ]

        for col_name, col_type in additions:
            if col_name not in existing_columns:
                connection.execute(text(f"ALTER TABLE downloads ADD COLUMN {col_name} {col_type}"))
                logger.info("Added missing column downloads.%s", col_name)

        # Create index if it doesn't exist (safe for both Postgres and SQLite)
        existing_indexes = {idx["name"] for idx in inspector.get_indexes("downloads")}
        if "idx_download_chat" not in existing_indexes:
            connection.execute(text("CREATE INDEX idx_download_chat ON downloads (chat_id)"))


def _ensure_data_dir() -> None:
    """Create the data directory for SQLite if needed."""
    if IS_SQLITE:
        db_path = settings.DATABASE_URL.replace("sqlite:///", "")
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)


def init_db():
    """Initialize the database schema and apply migrations."""
    _ensure_data_dir()

    if settings.DEV_MODE or IS_SQLITE:
        Base.metadata.create_all(bind=engine)
        return

    alembic_cfg = _get_alembic_config()
    existing_tables = set(inspect(engine).get_table_names())

    if not existing_tables:
        command.upgrade(alembic_cfg, "head")
        return

    if "alembic_version" not in existing_tables:
        _bootstrap_missing_tables()
        _repair_legacy_schema()
        command.stamp(alembic_cfg, "head")
        return

    command.upgrade(alembic_cfg, "head")


@contextmanager
def get_db() -> Session:
    """Get database session with automatic cleanup."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
