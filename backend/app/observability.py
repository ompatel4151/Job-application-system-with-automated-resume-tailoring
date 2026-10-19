"""Request IDs, JSON logs and Prometheus metrics.

Every request gets an ID: the one the frontend proxy sent in X-Request-ID if
it's a valid UUID, otherwise a new one. It goes back in the response header
and into every log line written while handling the request, so one user's
request can be followed from the Vercel logs to the backend logs.
"""

import json
import logging
import re
import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from prometheus_client import Counter, Histogram

REQUEST_ID: ContextVar[str | None] = ContextVar("request_id", default=None)
_UUID = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

request_log = logging.getLogger("app.request")

# Labels use route templates ("/api/applications/{application_id}"), never raw
# paths: one time series per id would grow without limit.
REQUESTS = Counter("http_requests_total", "Requests handled", ["method", "route", "status"])
ERRORS = Counter("http_errors_total", "4xx and 5xx responses", ["status_class"])
LATENCY = Histogram(
    "http_request_duration_seconds", "Time to respond", ["method", "route"],
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30),
)
RATE_LIMITED = Counter("rate_limit_rejections_total", "Requests refused with 429", ["bucket"])
REDIS_ERRORS = Counter("ratelimit_redis_errors_total", "Rate-limit checks that couldn't reach Redis")
LLM_LATENCY = Histogram(
    "llm_call_duration_seconds", "Time spent waiting for the LLM", ["provider", "operation"],
    buckets=(0.5, 1, 2.5, 5, 10, 20, 30, 60, 120),
)


def request_id_from(header: str | None) -> str:
    return header if header and _UUID.match(header) else str(uuid.uuid4())


class JsonFormatter(logging.Formatter):
    """One JSON object per line, which log tools (Render, CloudWatch) can search."""

    def format(self, record: logging.LogRecord) -> str:
        line = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or REQUEST_ID.get(),
        }
        if hasattr(record, "http"):
            line["http"] = record.http
        if record.exc_info:
            line["error"] = self.formatException(record.exc_info)
        return json.dumps(line, default=str)


def configure_logging() -> None:
    """JSON lines on stderr. Adds a handler rather than replacing the existing
    ones, so test log capture keeps working."""
    root = logging.getLogger()
    if not any(isinstance(h.formatter, JsonFormatter) for h in root.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonFormatter())
        root.addHandler(handler)
    root.setLevel(logging.INFO)


def record_request(method: str, route: str, status: int, seconds: float, user_id) -> None:
    REQUESTS.labels(method, route, str(status)).inc()
    LATENCY.labels(method, route).observe(seconds)
    if status >= 400:
        ERRORS.labels(f"{status // 100}xx").inc()
    request_log.info(
        "%s %s %s", method, route, status,
        extra={
            "request_id": REQUEST_ID.get(),
            "http": {
                "method": method,
                "route": route,
                "status": status,
                "duration_ms": round(seconds * 1000, 1),
                "user_id": str(user_id) if user_id else None,
            },
        },
    )


@contextmanager
def llm_timer(provider: str, operation: str):
    start = time.perf_counter()
    try:
        yield
    finally:
        LLM_LATENCY.labels(provider, operation).observe(time.perf_counter() - start)
