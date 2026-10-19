"""Alembic migrations build exactly the schema the models describe.

Runs on SQLite always, and also on Postgres when TEST_POSTGRES_URL is set
(CI sets it). The Postgres database is wiped before and after each test.
"""

import os

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text

from app.database import BASELINE, Base, _normalize, alembic_config, migrate

PG_URL = os.environ.get("TEST_POSTGRES_URL")
TABLES = {"applications", "resumes", "tailored_resumes", "idempotency_keys"}


def _wipe(url):
    engine = create_engine(_normalize(url))
    with engine.begin() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    engine.dispose()


@pytest.fixture(params=["sqlite", "postgres"])
def db_url(request, tmp_path):
    if request.param == "sqlite":
        yield f"sqlite:///{tmp_path}/migrations.db"
        return
    if not PG_URL:
        pytest.skip("TEST_POSTGRES_URL not set")
    _wipe(PG_URL)
    yield PG_URL
    _wipe(PG_URL)


def _drift(url):
    """What `alembic check` reports: differences between the DB and the models."""
    engine = create_engine(_normalize(url))
    with engine.connect() as conn:
        diff = compare_metadata(MigrationContext.configure(conn), Base.metadata)
    engine.dispose()
    return diff


def _tables(url):
    engine = create_engine(_normalize(url))
    names = set(inspect(engine).get_table_names())
    engine.dispose()
    return names


def test_upgrade_builds_exactly_the_models_schema(db_url):
    migrate(db_url)

    assert _tables(db_url) == TABLES | {"alembic_version"}
    assert _drift(db_url) == []


def test_downgrade_then_upgrade_round_trips(db_url):
    migrate(db_url)
    command.downgrade(alembic_config(db_url), "base")

    assert _tables(db_url) == {"alembic_version"}

    migrate(db_url)
    assert _drift(db_url) == []


def test_a_database_built_before_migrations_is_adopted(db_url):
    """The live database was made by create_all and has no alembic_version.
    Upgrading it must not try to create tables that already exist."""
    # Rebuild that state: the baseline schema with no version table.
    command.upgrade(alembic_config(db_url), BASELINE)
    engine = create_engine(_normalize(db_url))
    with engine.begin() as conn:
        conn.execute(text("DROP TABLE alembic_version"))
    engine.dispose()

    migrate(db_url)  # would raise "table already exists" without adoption

    assert _drift(db_url) == []


def test_postgres_tables_have_row_level_security_on(db_url):
    """Matches the live Supabase database, where RLS is on for all 4 tables."""
    if db_url.startswith("sqlite"):
        pytest.skip("RLS is Postgres-only")
    migrate(db_url)

    engine = create_engine(_normalize(db_url))
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT relname FROM pg_class WHERE relrowsecurity AND relkind = 'r'")
        ).scalars()
        assert set(rows) == TABLES
    engine.dispose()
