"""Per-user rate limiting with token buckets.

Each user has a bucket that holds up to `capacity` tokens and refills at a
steady rate. A request spends one token. If the bucket is empty, the request
gets a 429 with Retry-After saying when the next token arrives. Short bursts
up to `capacity` are allowed, but the long-run average can't exceed the
refill rate.

Limits live in this process's memory, so they are per server process. With N
processes or servers each one counts separately, which allows N times the
limit, and a restart resets every bucket. Sharing the counts (for example in
Redis) or limiting at a gateway in front of the app fixes that.
"""

import re
import time

from fastapi import Request

from app.config import settings

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


# Paid LLM calls get a strict budget; everything else a generous one. These
# numbers are design choices for a single-user app, not measured values.
LLM = TokenBucketLimiter(capacity=5, per_seconds=60)
API = TokenBucketLimiter(capacity=60, per_seconds=60)

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


def retry_after(request: Request) -> float:
    """Seconds the caller must wait, or 0 if this request may go ahead."""
    if (
        not settings.rate_limit_enabled
        or not request.url.path.startswith("/api")
        or request.method == "OPTIONS"
    ):
        return 0.0
    is_llm = request.method == "POST" and _LLM_ROUTE.match(request.url.path)
    limiter = LLM if is_llm else API
    return limiter.take(client_id(request))


def reset() -> None:
    """Empty all buckets (used between tests)."""
    LLM.reset()
    API.reset()
