"""Cursor pagination on the three list endpoints."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app import models
from app.pagination import MAX_LIMIT
from tests.tokens import USER_A

USER_A_UUID = uuid.UUID(USER_A)


def _walk(client, path, limit, **params):
    """Follow next_cursor to the end; returns every item in order."""
    items, cursor, pages = [], None, 0
    while True:
        query = {"limit": limit, **params, **({"cursor": cursor} if cursor else {})}
        body = client.get(path, params=query).json()
        items += body["items"]
        pages += 1
        cursor = body["next_cursor"]
        if cursor is None:
            return items, pages


def _seed_applications(db, n, same_time=False):
    """Insert directly, so timestamps can be controlled (and made equal)."""
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        at = base if same_time else base + timedelta(minutes=i)
        db.add(
            models.Application(
                user_id=USER_A_UUID, company=f"Co {i}", role="Dev",
                created_at=at, updated_at=at,
            )
        )
    db.commit()


def test_walking_every_page_returns_each_row_once_in_order(client, db):
    _seed_applications(db, 120)

    items, pages = _walk(client, "/api/applications", limit=25)

    assert pages == 5
    assert len(items) == 120
    assert len({a["id"] for a in items}) == 120
    assert [a["company"] for a in items] == [f"Co {i}" for i in range(119, -1, -1)]


def test_rows_with_the_same_timestamp_are_not_skipped_or_repeated(client, db):
    """The id tie-breaker is what makes this work."""
    _seed_applications(db, 30, same_time=True)

    items, _ = _walk(client, "/api/applications", limit=7)

    ids = [a["id"] for a in items]
    assert sorted(ids, reverse=True) == ids
    assert len(set(ids)) == 30


def test_default_page_and_last_page(client, make_application):
    for _ in range(3):
        make_application()

    body = client.get("/api/applications").json()

    assert len(body["items"]) == 3
    assert body["next_cursor"] is None


def test_status_filter_works_with_the_cursor(client, db):
    _seed_applications(db, 10)
    for a in db.query(models.Application).all()[:4]:
        a.status = models.ApplicationStatus.offer
    db.commit()

    items, _ = _walk(client, "/api/applications", limit=3, status="offer")

    assert len(items) == 4
    assert {a["status"] for a in items} == {"offer"}


@pytest.mark.parametrize("limit", [0, -1, MAX_LIMIT + 1])
def test_limit_out_of_range_is_422(client, limit):
    resp = client.get("/api/applications", params={"limit": limit})

    assert resp.status_code == 422
    assert resp.json()["errors"][0]["field"] == "query.limit"


@pytest.mark.parametrize("cursor", ["garbage", "e30", "WzEsMl0", "!!!"])
def test_a_bad_cursor_is_422(client, cursor):
    resp = client.get("/api/applications", params={"cursor": cursor})

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_resumes_and_tailored_lists_paginate_too(client, make_application, make_resume, fake_tailoring):
    for i in range(5):
        make_resume(name=f"R{i}", is_default=(i == 0))
    app_id = make_application()["id"]
    for _ in range(4):
        assert client.post(f"/api/applications/{app_id}/tailor", json={}).status_code == 201

    resumes, resume_pages = _walk(client, "/api/resumes", limit=2)
    tailored, tailored_pages = _walk(client, f"/api/applications/{app_id}/tailored", limit=3)

    assert [r["name"] for r in resumes] == ["R4", "R3", "R2", "R1", "R0"]
    assert resume_pages == 3
    assert len({t["id"] for t in tailored}) == 4
    assert tailored_pages == 2
