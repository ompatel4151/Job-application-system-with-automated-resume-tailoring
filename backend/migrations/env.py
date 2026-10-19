from alembic import context
from sqlalchemy import create_engine, text

from app import models  # noqa: F401  (registers the tables on Base.metadata)
from app.database import DATABASE_URL, Base

config = context.config

# The app passes the URL in; the alembic CLI falls back to DATABASE_URL.
engine = create_engine(config.get_main_option("sqlalchemy.url") or DATABASE_URL)
with engine.connect() as conn:
    context.configure(
        connection=conn,
        target_metadata=Base.metadata,
        # SQLite can't ALTER most things; batch mode copies the table instead.
        render_as_batch=conn.dialect.name == "sqlite",
    )
    with context.begin_transaction():
        if conn.dialect.name == "postgresql":
            # Several app instances may start at once. Only one migrates at a
            # time; the others wait, then find nothing left to do.
            conn.execute(text("SELECT pg_advisory_xact_lock(727274)"))
        context.run_migrations()
engine.dispose()
