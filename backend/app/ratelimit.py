"""Per-user rate limiting with token buckets.

Each user has a bucket that holds up to `capacity` tokens and refills at a
steady rate. A request spends one token. If the bucket is empty, the request
gets a 429 with Retry-After saying when the next token arrives. Short bursts
up to `capacity` are allowed, but the long-run average can't exceed the
refill rate.

With REDIS_URL set, buckets live in Redis, so every app instance spends from
the same bucket and a restart doesn't reset them. Without it (local dev,
tests), buckets live in this process's memory: with N processes each counts
separately, allowing N times the limit.
"""

import inspect
import logging
import re
import time

import redis.asyncio as aioredis
from fastapi import Request

from app.config import settings

logger = logging.getLogger(__name__)

# A burst of new client IPs would grow the bucket dict forever, so past this
# many clients we drop the ones that are idle (bucket already refilled).
MAX_CLIENTS = 10_000


class TokenBucketLimiter:
    def __init__(self, capacity: int, per_seconds: float, clock=time.monotonic):
        """Allow `capacity` requests per `per_seconds`, refilling smoothly."""
        self.capacity = capacity
        self.rate = capacity / per_seconds  # tokens added per second
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}  # client -> (tokens, at)

    def take(self, client: str) -> float:
        """Spend a token. Returns 0 if allowed, else seconds until one is free."""
        now = self.clock()
        tokens, at = self._buckets.get(client, (self.capacity, now))
        # Refill for the time since we last looked, up to the bucket size.
        tokens = min(self.capacity, tokens + (now - at) * self.rate)
        if tokens >= 1:
            self._buckets[client] = (tokens - 1, now)
            self._drop_idle_clients(now)
            return 0.0
        self._buckets[client] = (tokens, now)
        return (1 - tokens) / self.rate

    def _drop_idle_clients(self, now: float) -> None:
        if len(self._buckets) > MAX_CLIENTS:
            self._buckets = {
                client: (tokens, at)
                for client, (tokens, at) in self._buckets.items()
                if tokens + (now - at) * self.rate < self.capacity
            }

    def reset(self) -> None:
        self._buckets.clear()


# The same refill-then-spend as TokenBucketLimiter.take, as one Lua script:
# Redis runs a script without interleaving any other command, so two instances
# can never both read "1 token left" and both spend it.
_TAKE = """
local capacity = tonumber(ARGV[1])
local rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
if not now then
    -- Redis's clock, not each instance's, so instances whose clocks disagree
    -- still compute the same refill.
    local t = redis.call('TIME')
    now = tonumber(t[1]) + tonumber(t[2]) / 1000000
end
local state = redis.call('HMGET', KEYS[1], 'tokens', 'at')
local tokens = tonumber(state[1]) or capacity
local at = tonumber(state[2]) or now
tokens = math.min(capacity, tokens + math.max(0, now - at) * rate)
local wait = 0
if tokens >= 1 then
    tokens = tokens - 1
else
    wait = (1 - tokens) / rate
end
redis.call('HSET', KEYS[1], 'tokens', tokens, 'at', now)
-- Once it would be full again, the bucket is the same as a missing one.
redis.call('PEXPIRE', KEYS[1], math.ceil(capacity / rate * 1000))
-- As a string: Redis turns Lua numbers into integers, dropping the fraction.
return tostring(wait)
"""


class RedisTokenBucket:
    def __init__(self, capacity: int, per_seconds: float, client, name: str, clock=None):
        """Like TokenBucketLimiter, shared by every instance using `client`.
        `clock` exists for tests; normally Redis's own clock is used."""
        self.capacity = capacity
        self.rate = capacity / per_seconds
        self.name = name
        self.clock = clock
        self._script = client.register_script(_TAKE)

    async def take(self, client: str) -> float:
        now = self.clock() if self.clock else ""
        try:
            wait = await self._script(
                keys=[f"ratelimit:{self.name}:{client}"], args=[self.capacity, self.rate, now]
            )
        except aioredis.RedisError:
            # Fail open: a Redis outage shouldn't take the whole app down. The
            # cost is that limits stop working until Redis is back.
            logger.exception("Rate limiter can't reach Redis; allowing the request")
            return 0.0
        return float(wait)


def _limiter(capacity: int, per_seconds: float, name: str):
    if settings.redis_url:
        client = aioredis.from_url(
            settings.redis_url, socket_timeout=0.5, socket_connect_timeout=0.5
        )
        return RedisTokenBucket(capacity, per_seconds, client, name)
    return TokenBucketLimiter(capacity, per_seconds)


# Paid LLM calls get a strict budget; everything else a generous one. These
# numbers are design choices for a single-user app, not measured values.
LLM = _limiter(capacity=5, per_seconds=60, name="llm")
API = _limiter(capacity=60, per_seconds=60, name="api")

_LLM_ROUTE = re.compile(r"^/api/(applications/\d+/tailor|resumes/parse)$")


def client_id(request: Request) -> str:
    """Who is calling: the signed-in user (set by the auth middleware).

    Every /api request has one by the time it gets here. The IP fallback only
    applies if this is ever called without auth in front of it.
    """
    user_id = getattr(request.state, "user_id", None)
    if user_id is not None:
        return str(user_id)
    return request.client.host if request.client else "unknown"


async def retry_after(request: Request) -> float:
    """Seconds the caller must wait, or 0 if this request may go ahead."""
    if (
        not settings.rate_limit_enabled
        or not request.url.path.startswith("/api")
        or request.method == "OPTIONS"
    ):
        return 0.0
    is_llm = request.method == "POST" and _LLM_ROUTE.match(request.url.path)
    limiter = LLM if is_llm else API
    wait = limiter.take(client_id(request))
    return await wait if inspect.isawaitable(wait) else wait


def reset() -> None:
    """Empty all in-memory buckets (used between tests)."""
    LLM.reset()
    API.reset()
