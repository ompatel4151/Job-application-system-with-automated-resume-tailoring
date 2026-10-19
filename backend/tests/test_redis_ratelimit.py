"""Rate limits shared through Redis. Needs TEST_REDIS_URL (CI sets it)."""

import asyncio
import json
import os
import socket
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import httpx
import jwt
import pytest
import redis.asyncio as aioredis

from app import ratelimit
from tests.tokens import SIGNING_KEY, make_token

REDIS_URL = os.environ.get("TEST_REDIS_URL")
pytestmark = pytest.mark.skipif(not REDIS_URL, reason="TEST_REDIS_URL not set")
BACKEND = Path(__file__).resolve().parent.parent


def _bucket(capacity, per_seconds, clock=None):
    return ratelimit.RedisTokenBucket(
        capacity, per_seconds, aioredis.from_url(REDIS_URL), name="test", clock=clock
    )


@pytest.fixture(autouse=True)
def _empty_redis():
    asyncio.run(aioredis.from_url(REDIS_URL).flushdb())


# ---------- the same algorithm as the in-memory bucket ----------


def test_burst_then_wait(_empty_redis):
    now = [1000.0]
    bucket = _bucket(3, 3, clock=lambda: now[0])  # 1 token/s

    async def run():
        first = [await bucket.take("a") for _ in range(3)]
        blocked = await bucket.take("a")
        now[0] += 1.0
        refilled = await bucket.take("a")
        return first, blocked, refilled

    first, blocked, refilled = asyncio.run(run())
    assert first == [0, 0, 0]
    assert blocked == pytest.approx(1.0)
    assert refilled == 0


def test_concurrent_takes_never_overspend(_empty_redis):
    """50 at once against a 10-token bucket: exactly 10 get through. A separate
    GET then SET (not one atomic script) lets several read the same count."""
    bucket = _bucket(10, 3600)

    async def run():
        return await asyncio.gather(*(bucket.take("same-user") for _ in range(50)))

    results = asyncio.run(run())
    assert sum(1 for wait in results if wait == 0) == 10


def test_idle_buckets_expire(_empty_redis):
    bucket = _bucket(5, 60)
    asyncio.run(bucket.take("a"))

    ttl = asyncio.run(aioredis.from_url(REDIS_URL).pttl("ratelimit:test:a"))
    # Expires once it would be full again (5 tokens at 1 per 12 s), not never.
    assert 0 < ttl <= 60_000


def test_redis_down_fails_open():
    """An outage must not take the whole app down; requests are let through."""
    bucket = ratelimit.RedisTokenBucket(
        1, 60, aioredis.from_url("redis://127.0.0.1:1", socket_connect_timeout=0.2), name="down"
    )

    assert asyncio.run(bucket.take("a")) == 0


# ---------- two app processes, one Redis ----------


def _free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _serve_jwks():
    """The test signing key as a JWKS, like Supabase's, so real processes can
    verify test tokens without any monkeypatching."""
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(SIGNING_KEY.public_key()))
    body = json.dumps({"keys": [{**jwk, "kid": "test-key", "alg": "ES256", "use": "sig"}]}).encode()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _start_instances(tmp_path, supabase_url, redis_url):
    procs, ports = [], []
    for i in range(2):
        port = _free_port()
        env = {
            **os.environ,
            "DATABASE_URL": f"sqlite:///{tmp_path}/instance{i}.db",
            "SUPABASE_URL": supabase_url,
            "API_KEY": "",
        }
        env.pop("REDIS_URL", None)
        if redis_url:
            env["REDIS_URL"] = redis_url
        procs.append(
            subprocess.Popen(
                [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
                cwd=BACKEND, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
        )
        ports.append(port)
    for port in ports:
        for _ in range(100):
            try:
                if httpx.get(f"http://127.0.0.1:{port}/health").status_code == 200:
                    break
            except httpx.TransportError:
                time.sleep(0.1)
        else:
            raise RuntimeError(f"instance on {port} never came up")
    return procs, ports


def _hit_llm_bucket_alternately(tmp_path, redis_url):
    """10 tailor calls, alternating between the two instances. The bucket is
    spent before routing, so a missing application (404) still uses a token."""
    server, supabase_url = _serve_jwks()
    procs, ports = _start_instances(tmp_path, supabase_url, redis_url)
    try:
        token = make_token(iss=f"{supabase_url}/auth/v1")
        headers = {"Authorization": f"Bearer {token}"}
        codes = [
            httpx.post(
                f"http://127.0.0.1:{ports[i % 2]}/api/applications/999/tailor",
                json={}, headers=headers,
            ).status_code
            for i in range(10)
        ]
    finally:
        for p in procs:
            p.terminate()
            p.wait()
        server.shutdown()
    return codes


def test_two_instances_share_one_limit(tmp_path):
    codes = _hit_llm_bucket_alternately(tmp_path, REDIS_URL)

    # 5 per minute in total, not 5 per instance.
    assert codes.count(429) == 5
    assert codes.count(404) == 5


def test_without_redis_each_instance_counts_alone(tmp_path):
    """The control: the old in-memory limiter allows 5 per instance, 10 total.
    This is the gap that sharing through Redis closes."""
    codes = _hit_llm_bucket_alternately(tmp_path, None)

    assert codes.count(429) == 0
