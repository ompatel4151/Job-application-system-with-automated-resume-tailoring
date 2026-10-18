"""Rate limiting: a token bucket per client, and a 429 with Retry-After when empty."""

import math

import pytest

from app import ratelimit
from app.config import settings


@pytest.fixture
def clock(monkeypatch):
    """A fake clock, so refill timing is exact instead of sleeping in tests."""
    now = [1000.0]
    for limiter in (ratelimit.LLM, ratelimit.API):
        monkeypatch.setattr(limiter, "clock", lambda: now[0])
    return now


@pytest.fixture
def tiny_api_bucket(monkeypatch, clock):
    """Swap the general bucket for a 1-request one, so it's quick to empty."""
    monkeypatch.setattr(
        ratelimit, "API", ratelimit.TokenBucketLimiter(1, 60, clock=lambda: clock[0])
    )


# ---------- the algorithm on its own ----------


def test_bucket_allows_a_burst_then_says_how_long_to_wait(clock):
    bucket = ratelimit.TokenBucketLimiter(3, 3, clock=lambda: clock[0])  # 1 token/s

    assert [bucket.take("a") for _ in range(3)] == [0, 0, 0]
    assert bucket.take("a") == pytest.approx(1.0)


def test_bucket_refills_over_time(clock):
    bucket = ratelimit.TokenBucketLimiter(3, 3, clock=lambda: clock[0])
    for _ in range(3):
        bucket.take("a")

    clock[0] += 1.0  # one second = one token back

    assert bucket.take("a") == 0
    assert bucket.take("a") > 0


def test_each_client_has_its_own_bucket(clock):
    bucket = ratelimit.TokenBucketLimiter(1, 60, clock=lambda: clock[0])

    assert bucket.take("a") == 0
    assert bucket.take("a") > 0
    assert bucket.take("b") == 0


# ---------- through the API ----------


def _tailor(client, app_id):
    return client.post(f"/api/applications/{app_id}/tailor", json={})


def _exhaust_llm_bucket(client, app_id):
    for _ in range(int(ratelimit.LLM.capacity)):
        assert _tailor(client, app_id).status_code == 201


def test_llm_endpoint_returns_429_with_retry_after(
    client, clock, make_application, make_resume, fake_tailoring
):
    make_resume()
    app_id = make_application()["id"]
    _exhaust_llm_bucket(client, app_id)

    resp = _tailor(client, app_id)

    assert resp.status_code == 429
    assert resp.json()["code"] == "rate_limited"
    # One token comes back every 1/rate seconds.
    assert int(resp.headers["Retry-After"]) == math.ceil(1 / ratelimit.LLM.rate)


def test_waiting_lets_requests_through_again(
    client, clock, make_application, make_resume, fake_tailoring
):
    make_resume()
    app_id = make_application()["id"]
    _exhaust_llm_bucket(client, app_id)

    clock[0] += 1 / ratelimit.LLM.rate

    assert _tailor(client, app_id).status_code == 201


def test_crud_has_its_own_bucket(
    client, clock, make_application, make_resume, fake_tailoring
):
    """Running out of LLM calls must not lock you out of your own data."""
    make_resume()
    app_id = make_application()["id"]
    _exhaust_llm_bucket(client, app_id)

    assert client.get("/api/applications").status_code == 200


def test_429_message_uses_singular_for_one_second(client, monkeypatch, clock):
    """Seen live: "Try again in 1 seconds." A 60/min bucket refills 1 token/s."""
    monkeypatch.setattr(
        ratelimit, "API", ratelimit.TokenBucketLimiter(1, 1, clock=lambda: clock[0])
    )
    client.get("/api/applications")

    resp = client.get("/api/applications")

    assert resp.json()["detail"] == "Too many requests. Try again in 1 second."


def test_health_is_never_limited(client, tiny_api_bucket):
    client.get("/api/applications")  # uses the only token

    assert client.get("/api/applications").status_code == 429
    assert client.get("/health").status_code == 200


def test_forwarded_ip_is_trusted_from_the_authenticated_proxy(
    client, tiny_api_bucket, monkeypatch
):
    """Behind our proxy, each end user gets their own bucket."""
    monkeypatch.setattr(settings, "api_key", "s3cret")
    monkeypatch.setattr(settings, "trust_forwarded_for", True)

    def get(ip):
        headers = {"X-API-Key": "s3cret", "X-Forwarded-For": ip}
        return client.get("/api/applications", headers=headers).status_code

    assert get("1.1.1.1") == 200
    assert get("2.2.2.2") == 200  # a different user, their own bucket
    assert get("1.1.1.1") == 429


def test_spoofed_forwarded_ip_is_ignored_without_the_key(
    client, tiny_api_bucket, monkeypatch
):
    """A caller can't get a fresh bucket by inventing a new X-Forwarded-For."""
    monkeypatch.setattr(settings, "trust_forwarded_for", True)

    client.get("/api/applications", headers={"X-Forwarded-For": "1.1.1.1"})
    resp = client.get("/api/applications", headers={"X-Forwarded-For": "9.9.9.9"})

    assert resp.status_code == 429


def test_rate_limiting_can_be_turned_off(client, tiny_api_bucket, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_enabled", False)

    for _ in range(3):
        assert client.get("/api/applications").status_code == 200
