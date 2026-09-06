"""The optional API-key gate on /api routes."""

from app.config import settings


def test_api_is_open_when_no_key_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", None)
    assert client.get("/api/applications").status_code == 200


def test_api_requires_key_when_configured(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "s3cret")
    assert client.get("/api/applications").status_code == 401
    assert client.get("/api/applications", headers={"X-API-Key": "wrong"}).status_code == 401
    ok = client.get("/api/applications", headers={"X-API-Key": "s3cret"})
    assert ok.status_code == 200


def test_health_is_never_gated(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "s3cret")
    assert client.get("/health").status_code == 200
