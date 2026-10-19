"""Accounts: every /api request needs a valid Supabase token, and each user
only ever sees and changes their own rows."""

import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app import ratelimit
from app.config import settings
from tests.tokens import USER_B, auth_header, make_token

AS_B = auth_header(USER_B)


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


# ---------- the token check ----------


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": ""},
        {"Authorization": "Bearer"},
        {"Authorization": "Bearer not-a-jwt"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        _bearer(make_token(exp=1)),  # expired
        _bearer(make_token(aud="anon")),  # not a signed-in user's token
        _bearer(make_token(iss="https://other-project.supabase.co/auth/v1")),
        _bearer(make_token(sub=None)),  # no user id
        _bearer(make_token(sub="not-a-uuid")),
        _bearer(make_token(key=ec.generate_private_key(ec.SECP256R1()))),  # forged
    ],
    ids=[
        "empty", "no-token", "garbage", "basic", "expired", "wrong-aud",
        "wrong-issuer", "no-sub", "bad-sub", "wrong-key",
    ],
)
def test_bad_tokens_get_401(client, headers):
    resp = client.get("/api/applications", headers=headers)

    assert resp.status_code == 401
    assert resp.json()["code"] == "unauthorized"


def test_alg_none_is_rejected(client):
    header = "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0"  # {"alg":"none","typ":"JWT"}
    payload = make_token().split(".")[1]
    resp = client.get("/api/applications", headers=_bearer(f"{header}.{payload}."))

    assert resp.status_code == 401


def test_auth_is_required_even_with_no_supabase_configured(client, monkeypatch):
    """Misconfiguration must fail closed, not open."""
    monkeypatch.setattr(settings, "supabase_url", None)

    assert client.get("/api/applications").status_code == 401


def test_health_needs_no_token(client):
    assert client.get("/health", headers={"Authorization": ""}).status_code == 200


def test_api_key_is_still_checked_alongside_the_token(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "s3cret")

    assert client.get("/api/applications").status_code == 401
    ok = client.get("/api/applications", headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200


# ---------- user A vs user B, through the API ----------


@pytest.fixture
def a_data(client, make_application, make_resume, fake_tailoring):
    """One of everything, owned by user A."""
    resume = make_resume()
    application = make_application()
    tailored = client.post(f"/api/applications/{application['id']}/tailor", json={})
    assert tailored.status_code == 201
    return {"app": application["id"], "resume": resume["id"], "tailored": tailored.json()["id"]}


def test_b_cannot_read_a_s_rows(client, a_data):
    a, r, t = a_data["app"], a_data["resume"], a_data["tailored"]
    for path in (
        f"/api/applications/{a}",
        f"/api/applications/{a}/tailored",
        f"/api/resumes/{r}",
        f"/api/tailored/{t}",
        f"/api/tailored/{t}/markdown",
    ):
        # 404, not 403: B can't even learn that the id exists.
        assert client.get(path, headers=AS_B).status_code == 404, path


def test_b_s_lists_and_stats_leave_out_a_s_rows(client, a_data):
    assert client.get("/api/applications", headers=AS_B).json()["items"] == []
    assert client.get("/api/resumes", headers=AS_B).json()["items"] == []
    assert client.get("/api/applications/stats", headers=AS_B).json()["total"] == 0

    assert len(client.get("/api/applications").json()["items"]) == 1  # A still sees theirs


def test_b_cannot_change_or_delete_a_s_rows(client, a_data, fake_tailoring):
    a, r = a_data["app"], a_data["resume"]

    assert client.patch(f"/api/applications/{a}", json={"company": "Hacked"}, headers=AS_B).status_code == 404
    assert client.put(f"/api/resumes/{r}", json={"name": "Hacked"}, headers=AS_B).status_code == 404
    assert client.post(f"/api/applications/{a}/tailor", json={}, headers=AS_B).status_code == 404
    assert client.delete(f"/api/applications/{a}", headers=AS_B).status_code == 404
    assert client.delete(f"/api/resumes/{r}", headers=AS_B).status_code == 404

    assert client.get(f"/api/applications/{a}").json()["company"] == "Globex"
    assert client.get(f"/api/resumes/{r}").json()["name"] == "Base resume"


def test_b_cannot_tailor_with_a_s_resume(client, a_data, sample_resume_content, fake_tailoring):
    b_app = client.post(
        "/api/applications",
        json={"company": "B Corp", "role": "Dev", "job_description": "Python"},
        headers=AS_B,
    ).json()

    resp = client.post(
        f"/api/applications/{b_app['id']}/tailor",
        json={"resume_id": a_data["resume"]},
        headers=AS_B,
    )
    assert resp.status_code == 404
    # And A's default resume isn't B's default either.
    resp = client.post(f"/api/applications/{b_app['id']}/tailor", json={}, headers=AS_B)
    assert resp.status_code == 400


def test_making_a_default_resume_does_not_touch_other_users(client, make_resume, sample_resume_content):
    a_resume = make_resume(is_default=True)
    client.post(
        "/api/resumes",
        json={"name": "B's", "is_default": True, "content": sample_resume_content},
        headers=AS_B,
    )

    assert client.get(f"/api/resumes/{a_resume['id']}").json()["is_default"] is True


def test_same_idempotency_key_for_two_users_is_two_requests(client):
    """Keys are per user. Otherwise B could replay A's stored response."""
    body = {"company": "Globex", "role": "Backend Engineer"}
    key = {"Idempotency-Key": "shared-key"}

    a = client.post("/api/applications", json=body, headers=key)
    b = client.post("/api/applications", json=body, headers={**key, **AS_B})

    assert a.status_code == b.status_code == 201
    assert "Idempotent-Replayed" not in b.headers
    assert a.json()["id"] != b.json()["id"]
    assert len(client.get("/api/applications", headers=AS_B).json()["items"]) == 1


def test_rate_limit_buckets_are_per_user(client, monkeypatch):
    monkeypatch.setattr(ratelimit, "API", ratelimit.TokenBucketLimiter(1, 60))

    assert client.get("/api/applications").status_code == 200
    assert client.get("/api/applications").status_code == 429
    assert client.get("/api/applications", headers=AS_B).status_code == 200

