"""Row-level security on Postgres: even with no WHERE clause, a signed-in user
only reaches their own rows. Needs TEST_POSTGRES_URL (CI sets it)."""

import json
import os

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import sessionmaker

from app.database import _normalize, get_db, migrate
from app.main import app
from tests.test_migrations import _wipe
from tests.tokens import USER_A, USER_B, auth_header

PG_URL = os.environ.get("TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(not PG_URL, reason="TEST_POSTGRES_URL not set")


@pytest.fixture
def pg():
    _wipe(PG_URL)
    migrate(PG_URL)
    engine = create_engine(_normalize(PG_URL))
    # As the owner (RLS doesn't apply): one application and resume per user.
    with engine.begin() as conn:
        for user, company in ((USER_A, "A Corp"), (USER_B, "B Corp")):
            conn.execute(
                text(
                    "INSERT INTO applications (user_id, company, role, status, created_at, updated_at) "
                    "VALUES (:u, :c, 'Dev', 'saved', now(), now())"
                ),
                {"u": user, "c": company},
            )
            conn.execute(
                text(
                    "INSERT INTO resumes (user_id, name, is_default, content, created_at, updated_at) "
                    "VALUES (:u, :c, true, '{}', now(), now())"
                ),
                {"u": user, "c": company},
            )
    yield engine
    engine.dispose()
    _wipe(PG_URL)


def _as(conn, user):
    """What Supabase's API, and our backend, do for a signed-in request."""
    conn.execute(
        text("SELECT set_config('role', 'authenticated', true), set_config('request.jwt.claims', :c, true)"),
        {"c": json.dumps({"sub": user, "role": "authenticated"})},
    )


def test_select_without_a_filter_only_returns_your_rows(pg):
    with pg.begin() as conn:
        _as(conn, USER_A)
        companies = conn.execute(text("SELECT company FROM applications")).scalars().all()
        resumes = conn.execute(text("SELECT name FROM resumes")).scalars().all()

    assert companies == ["A Corp"]
    assert resumes == ["A Corp"]


def test_update_and_delete_cannot_reach_other_users_rows(pg):
    with pg.begin() as conn:
        _as(conn, USER_A)
        updated = conn.execute(text("UPDATE applications SET company = 'Hacked' WHERE company = 'B Corp'"))
        deleted = conn.execute(text("DELETE FROM resumes WHERE name = 'B Corp'"))
        assert updated.rowcount == 0
        assert deleted.rowcount == 0

    with pg.connect() as conn:  # as the owner again: B's rows are untouched
        assert conn.execute(text("SELECT count(*) FROM applications WHERE company = 'B Corp'")).scalar() == 1
        assert conn.execute(text("SELECT count(*) FROM resumes WHERE name = 'B Corp'")).scalar() == 1


def test_you_cannot_insert_a_row_owned_by_someone_else(pg):
    with pytest.raises(DBAPIError, match="row-level security"):
        with pg.begin() as conn:
            _as(conn, USER_A)
            conn.execute(
                text(
                    "INSERT INTO applications (user_id, company, role, status, created_at, updated_at) "
                    "VALUES (:u, 'Planted', 'Dev', 'saved', now(), now())"
                ),
                {"u": USER_B},
            )


def test_no_claims_means_no_rows(pg):
    """The authenticated role with no user id (a bug upstream) sees nothing."""
    with pg.begin() as conn:
        conn.execute(text("SELECT set_config('role', 'authenticated', true)"))
        assert conn.execute(text("SELECT count(*) FROM applications")).scalar() == 0


def test_the_api_on_postgres_keeps_users_apart(pg):
    """End to end: tokens, the per-request role switch, and the policies."""
    Session = sessionmaker(bind=pg, autoflush=False)

    def pg_db(request: Request):
        db = Session(info={"user_id": request.state.user_id})
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = pg_db
    try:
        with TestClient(app) as c:
            as_a, as_b = auth_header(USER_A), auth_header(USER_B)
            created = c.post(
                "/api/applications", json={"company": "Via API", "role": "Dev"}, headers=as_a
            )
            assert created.status_code == 201
            new_id = created.json()["id"]

            a_list = c.get("/api/applications", headers=as_a).json()
            b_list = c.get("/api/applications", headers=as_b).json()
            assert sorted(a["company"] for a in a_list) == ["A Corp", "Via API"]
            assert [a["company"] for a in b_list] == ["B Corp"]
            assert c.get(f"/api/applications/{new_id}", headers=as_b).status_code == 404
            assert c.delete(f"/api/applications/{new_id}", headers=as_b).status_code == 404
    finally:
        app.dependency_overrides.clear()
