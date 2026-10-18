from app.database import _normalize

PSYCOPG2_URL = "postgresql+psycopg2://user:pw@host:5432/postgres"


def test_normalize_names_the_installed_psycopg2_driver():
    """A bare URL lets SQLAlchemy pick the driver. SQLAlchemy 2.1 switched its
    default to psycopg 3, which isn't installed, and the October 2026 Render
    deploy crashed at import with ModuleNotFoundError: psycopg."""
    for url in (
        "postgres://user:pw@host:5432/postgres",  # legacy Render/Heroku scheme
        "postgresql://user:pw@host:5432/postgres",
    ):
        assert _normalize(url) == PSYCOPG2_URL


def test_normalize_leaves_other_urls_alone():
    for url in (
        PSYCOPG2_URL,
        "postgresql+psycopg://user:pw@host:5432/postgres",  # an explicit choice is kept
        "sqlite:///./job_tracker.db",
    ):
        assert _normalize(url) == url


def test_normalize_only_rewrites_the_scheme():
    """A password containing the literal string must not be mangled."""
    url = "postgres://user:postgres://@host:5432/db"
    assert _normalize(url) == "postgresql+psycopg2://user:postgres://@host:5432/db"


def test_tailored_resumes_are_indexed_by_application():
    """Milestone 6: without this index, each detail page scanned the whole table."""
    from app.models import TailoredResume

    indexed = {col.name for idx in TailoredResume.__table__.indexes for col in idx.columns}
    assert "application_id" in indexed
