from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings


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
