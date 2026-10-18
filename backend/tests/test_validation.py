"""Input validation and one consistent error shape: {"detail": str, "code": str}."""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app

VALID = {"company": "Acme", "role": "SWE"}


def _create(client, **fields):
    return client.post("/api/applications", json={**VALID, **fields})


@pytest.mark.parametrize(
    "fields, bad_field",
    [
        ({"company": ""}, "company"),
        ({"company": "   "}, "company"),  # whitespace only
        ({"role": ""}, "role"),
        ({"company": "x" * 201}, "company"),  # column is VARCHAR(200)
        ({"job_url": "javascript:alert(1)"}, "job_url"),
        ({"job_url": "not a url"}, "job_url"),
        ({"job_description": "x" * 20_001}, "job_description"),
    ],
)
def test_bad_input_is_rejected_with_the_field_named(client, fields, bad_field):
    resp = _create(client, **fields)

    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["detail"], str)
    assert bad_field in [e["field"] for e in body["errors"]]


def test_values_at_the_limits_are_accepted(client):
    resp = _create(
        client,
        company="x" * 200,
        job_url="https://example.com/jobs/1",
        job_description="x" * 20_000,
    )
    assert resp.status_code == 201


def test_patch_null_on_required_field_returns_422(client, make_application):
    """AUDIT #4: an explicit null used to reach the database and return 500."""
    app_data = make_application()

    resp = client.patch(f"/api/applications/{app_data['id']}", json={"company": None})

    assert resp.status_code == 422
    assert resp.json()["code"] == "validation_error"


def test_patch_null_on_an_optional_field_clears_it(client, make_application):
    app_data = make_application(job_url="https://example.com/job")

    resp = client.patch(f"/api/applications/{app_data['id']}", json={"job_url": None})

    assert resp.status_code == 200
    assert resp.json()["job_url"] is None


@pytest.mark.parametrize(
    "method, path, status, code",
    [
        ("get", "/api/applications/999", 404, "not_found"),
        ("get", "/api/no-such-route", 404, "not_found"),
        ("post", "/api/applications", 422, "validation_error"),
    ],
)
def test_errors_share_one_shape(client, method, path, status, code):
    resp = client.request(method, path, json={})

    assert resp.status_code == status
    body = resp.json()
    assert body["code"] == code
    assert isinstance(body["detail"], str)


def test_auth_error_shares_the_shape(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "s3cret")

    body = client.get("/api/applications").json()

    assert body == {"detail": "Invalid or missing API key.", "code": "unauthorized"}


def test_unexpected_errors_return_a_generic_500(client, monkeypatch):
    """No stack trace or internal detail leaks to the client."""

    def boom(*args, **kwargs):
        raise RuntimeError("database password is hunter2")

    monkeypatch.setattr("app.routers.applications._tailored_counts", boom)
    # The `client` fixture installs the in-memory DB. This second client just
    # turns off re-raising, so we see the 500 response the user would get.
    raw = TestClient(app, raise_server_exceptions=False)
    resp = raw.get("/api/applications")

    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error", "code": "internal_error"}


def test_match_score_is_clamped_to_0_100(monkeypatch, sample_resume_content):
    from app.schemas import MatchAnalysis, ResumeContent
    from app.services import tailoring

    def over_eager_model(base, prompt):
        return tailoring.TailoringResult(
            tailored_resume=ResumeContent.model_validate(sample_resume_content),
            match_analysis=MatchAnalysis(match_score=150),
        )

    monkeypatch.setattr(settings, "llm_provider", "claude")
    monkeypatch.setattr(tailoring, "_tailor_with_claude", over_eager_model)

    result = tailoring.tailor_resume(sample_resume_content, "JD", "Acme", "SWE")

    assert result.match_analysis.match_score == 100
