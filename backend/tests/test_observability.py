"""Request IDs, one structured log line per request, and Prometheus metrics."""

import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app import observability, ratelimit
from app.config import settings
from app.main import app
from tests.tokens import USER_A, auth_header

GOOD_ID = "0b6e7c1a-3f7d-4c1e-9a7e-2f1d6c5b4a39"


def _sample(name, **labels):
    return REGISTRY.get_sample_value(name, labels) or 0.0


# ---------- request IDs ----------


def test_a_valid_request_id_is_kept(client):
    resp = client.get("/api/applications", headers={"X-Request-ID": GOOD_ID})

    assert resp.headers["X-Request-ID"] == GOOD_ID


@pytest.mark.parametrize("sent", [None, "not-a-uuid", "x" * 500, "a\nb"])
def test_a_missing_or_bad_request_id_is_replaced(client, sent):
    headers = {"X-Request-ID": sent} if sent is not None else {}
    resp = client.get("/api/applications", headers=headers)

    returned = resp.headers["X-Request-ID"]
    assert returned != sent
    uuid.UUID(returned)  # a fresh UUID


def test_error_responses_carry_the_request_id_too(client):
    resp = client.get("/api/applications", headers={"Authorization": "", "X-Request-ID": GOOD_ID})

    assert resp.status_code == 401
    assert resp.headers["X-Request-ID"] == GOOD_ID


# ---------- logs ----------


def test_one_log_line_per_request_with_the_route_template(client, caplog, make_application):
    app_id = make_application()["id"]
    caplog.set_level(logging.INFO, logger="app.request")
    caplog.clear()

    client.get(f"/api/applications/{app_id}", headers={"X-Request-ID": GOOD_ID})

    [record] = [r for r in caplog.records if r.name == "app.request"]
    assert record.http == {
        "method": "GET",
        "route": "/api/applications/{application_id}",
        "status": 200,
        "duration_ms": record.http["duration_ms"],
        "user_id": USER_A,
    }
    assert record.request_id == GOOD_ID


def test_the_formatter_writes_json_with_the_request_id():
    token = observability.REQUEST_ID.set(GOOD_ID)
    try:
        record = logging.LogRecord("app.x", logging.WARNING, __file__, 1, "Hello %s", ("you",), None)
        record.http = {"status": 500}
        line = json.loads(observability.JsonFormatter().format(record))
    finally:
        observability.REQUEST_ID.reset(token)

    assert line["message"] == "Hello you"
    assert line["level"] == "WARNING"
    assert line["request_id"] == GOOD_ID
    assert line["http"] == {"status": 500}


def test_tokens_never_reach_the_log(client, caplog):
    caplog.set_level(logging.INFO, logger="app.request")
    token = auth_header()["Authorization"].split()[1]

    client.get("/api/applications")

    assert token not in caplog.text
    assert all(token not in json.dumps(r.__dict__, default=str) for r in caplog.records)


# ---------- metrics ----------


@pytest.fixture
def metrics_client(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "s3cret")
    return lambda: client.get("/metrics", headers={"X-API-Key": "s3cret"})


def test_metrics_need_the_api_key(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "s3cret")
    assert client.get("/metrics").status_code == 401
    assert client.get("/metrics", headers={"X-API-Key": "s3cret"}).status_code == 200


def test_metrics_are_closed_when_no_api_key_is_set(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", None)
    assert client.get("/metrics").status_code == 401


def test_requests_are_counted_by_route_template_not_raw_path(client, metrics_client):
    """Raw paths would make a new time series per id and grow forever."""
    labels = {"method": "GET", "route": "/api/applications/{application_id}", "status": "404"}
    before = _sample("http_requests_total", **labels)

    client.get("/api/applications/123", headers={"X-API-Key": "s3cret"})
    client.get("/api/applications/456", headers={"X-API-Key": "s3cret"})

    assert _sample("http_requests_total", **labels) == before + 2
    body = metrics_client().text
    assert "/api/applications/123" not in body


def test_latency_is_observed(client, metrics_client):
    labels = {"method": "GET", "route": "/api/applications/stats"}
    before = _sample("http_request_duration_seconds_count", **labels)

    client.get("/api/applications/stats", headers={"X-API-Key": "s3cret"})

    assert _sample("http_request_duration_seconds_count", **labels) == before + 1


def test_4xx_and_5xx_are_counted(client, monkeypatch, metrics_client):
    before_4xx = _sample("http_errors_total", status_class="4xx")
    before_5xx = _sample("http_errors_total", status_class="5xx")

    def boom(*args, **kwargs):
        raise RuntimeError("database exploded")

    monkeypatch.setattr("app.routers.applications._tailored_counts", boom)
    raw = TestClient(app, raise_server_exceptions=False, headers={**auth_header(), "X-API-Key": "s3cret"})
    assert raw.get("/api/applications").status_code == 500
    assert client.get("/api/applications/999", headers={"X-API-Key": "s3cret"}).status_code == 404

    assert _sample("http_errors_total", status_class="5xx") == before_5xx + 1
    assert _sample("http_errors_total", status_class="4xx") == before_4xx + 1


def test_rate_limit_rejections_are_counted_by_bucket(client, monkeypatch, metrics_client):
    monkeypatch.setattr(ratelimit, "API", ratelimit.TokenBucketLimiter(1, 60))
    before = _sample("rate_limit_rejections_total", bucket="api")

    client.get("/api/applications", headers={"X-API-Key": "s3cret"})
    assert client.get("/api/applications", headers={"X-API-Key": "s3cret"}).status_code == 429

    assert _sample("rate_limit_rejections_total", bucket="api") == before + 1


def test_llm_call_latency_is_observed(client, make_application, make_resume, fake_tailoring):
    make_resume()
    app_id = make_application()["id"]
    labels = {"provider": settings.resolve_provider(), "operation": "tailor"}
    before = _sample("llm_call_duration_seconds_count", **labels)

    assert client.post(f"/api/applications/{app_id}/tailor", json={}).status_code == 201

    assert _sample("llm_call_duration_seconds_count", **labels) == before + 1
