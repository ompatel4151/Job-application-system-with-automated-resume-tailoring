import json
from pathlib import Path

from fastapi import HTTPException, Request
from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

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


def get_db(request: Request):
    # The auth middleware has set the caller; RLS below runs as them.
    db = SessionLocal(info={"user_id": getattr(request.state, "user_id", None)})
    try:
        yield db
    finally:
        db.close()


@event.listens_for(Session, "after_begin")
def _act_as_user(session, transaction, connection):
    """Run every transaction as the signed-in user, so Postgres RLS applies.

    The backend connects as the tables' owner, which RLS ignores. Switching to
    the `authenticated` role with the user's claims (what Supabase's own API
    does) means a query that forgets its user_id filter still can't reach
    another user's rows. Both settings are transaction-local, so a pooled
    connection never carries them into the next request.
    """
    user_id = session.info.get("user_id")
    if user_id is None or connection.dialect.name != "postgresql":
        return
    claims = json.dumps({"sub": str(user_id), "role": "authenticated"})
    connection.execute(
        text(
            "SELECT set_config('role', 'authenticated', true), "
            "set_config('request.jwt.claims', :claims, true)"
        ),
        {"claims": claims},
    )


def get_owned(db: Session, model, row_id, user_id, name: str):
    """The row if it exists and belongs to user_id, else 404 either way, so an
    id that belongs to someone else looks exactly like one that doesn't exist."""
    row = db.get(model, row_id)
    if row is None or row.user_id != user_id:
        raise HTTPException(404, f"{name} not found")
    return row


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
