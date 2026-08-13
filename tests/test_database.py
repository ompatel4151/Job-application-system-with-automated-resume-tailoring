from app.database import _normalize


def test_normalize_rewrites_legacy_postgres_scheme():
    url = "postgres://user:pw@host:5432/postgres"
    assert _normalize(url) == "postgresql://user:pw@host:5432/postgres"


def test_normalize_leaves_other_urls_alone():
    for url in (
        "postgresql://user:pw@host:5432/postgres",
        "sqlite:///./job_tracker.db",
    ):
        assert _normalize(url) == url


def test_normalize_only_rewrites_the_scheme():
    """A password containing the literal string must not be mangled."""
    url = "postgres://user:postgres://@host:5432/db"
    assert _normalize(url) == "postgresql://user:postgres://@host:5432/db"
