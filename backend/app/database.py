from pathlib import Path

from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"
BASELINE = "0001"


def _normalize(url: str) -> str:
    """Make a Postgres URL name the driver we actually install (psycopg2).

    Render/Heroku hand out postgres://, which SQLAlchemy 2 rejects. A bare
    postgresql:// lets SQLAlchemy pick the driver, and SQLAlchemy 2.1 changed
    that default to psycopg 3, which isn't installed. URLs that already name a
    driver (postgresql+...://) are left alone.
    """
    for scheme in ("postgres://", "postgresql://"):
        if url.startswith(scheme):
            return "postgresql+psycopg2://" + url[len(scheme):]
    return url


DATABASE_URL = _normalize(settings.database_url)

if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
else:
    # Managed Postgres (Supabase pooler) drops idle connections; pre-ping so a
    # stale pooled connection is replaced instead of surfacing as a 500.
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def alembic_config(url: str | None = None):
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    # Config values go through configparser, where % is special.
    cfg.set_main_option("sqlalchemy.url", _normalize(url or DATABASE_URL).replace("%", "%%"))
    return cfg


def migrate(url: str | None = None) -> None:
    """Bring the schema up to date.

    A database built by create_all before migrations existed (the live one)
    has the tables but no alembic_version. It already matches the baseline, so
    it's stamped as baseline instead of having its tables created again.
    """
    from alembic import command

    cfg = alembic_config(url)
    probe = create_engine(cfg.get_main_option("sqlalchemy.url"))
    tables = set(inspect(probe).get_table_names())
    probe.dispose()
    if "applications" in tables and "alembic_version" not in tables:
        command.stamp(cfg, BASELINE)
    command.upgrade(cfg, "head")
