import logging
import math
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import auth, ratelimit
from app.config import settings
from app.database import migrate
from app.routers import applications, resumes, tailoring

logger = logging.getLogger(__name__)

CREATE_RETRIES = 5
RETRY_DELAY_SECONDS = 2

# Every error response has the same shape: {"detail": <human message>,
# "code": <machine-readable>}. 422s add "errors": [{"field", "message"}].
# "detail" stays a string so existing clients that show it keep working.
ERROR_CODES = {
    400: "bad_request",
    401: "unauthorized",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "rate_limited",
    500: "internal_error",
    502: "upstream_error",
}


def error_response(status: int, detail: str, headers=None, **extra) -> JSONResponse:
    body = {"detail": detail, "code": ERROR_CODES.get(status, "error"), **extra}
    return JSONResponse(body, status_code=status, headers=headers)


def init_db(retries: int = CREATE_RETRIES, delay: float = RETRY_DELAY_SECONDS) -> None:
    """Run migrations, tolerating a database that is still waking up.

    Managed Postgres instances can refuse the first connection after a cold
    start; without the retry a transient blip takes the whole app down at boot.
    """
    for attempt in range(1, retries + 1):
        try:
            migrate()
            return
        except OperationalError:
            if attempt == retries:
                raise
            logger.warning(
                "Database not ready (attempt %s/%s); retrying in %ss",
                attempt,
                retries,
                delay,
            )
            time.sleep(delay)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Job Application Tracker",
    description="Track job applications and generate resumes tailored to each "
    "job description with an LLM. Every /api route needs a Supabase access token.",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Registered first, so it runs second (Starlette runs the last-added middleware
# first): it needs the user id that authenticate sets.
@app.middleware("http")
async def rate_limit(request: Request, call_next):
    wait = await ratelimit.retry_after(request)
    if wait:
        seconds = math.ceil(wait)
        return error_response(
            429,
            f"Too many requests. Try again in {seconds} second{'' if seconds == 1 else 's'}.",
            headers={"Retry-After": str(seconds)},
        )
    return await call_next(request)


@app.middleware("http")
async def authenticate(request: Request, call_next):
    """Every /api request needs the proxy's API key (when one is set) and a
    signed-in user's token. Preflight OPTIONS requests pass, or CORS breaks."""
    if request.url.path.startswith("/api") and request.method != "OPTIONS":
        if settings.api_key and not settings.api_key_matches(request.headers.get("x-api-key")):
            return error_response(401, "Invalid or missing API key.")
        try:
            request.state.user_id = auth.user_id_from(request.headers.get("authorization"))
        except auth.Unauthorized as exc:
            return error_response(401, str(exc))
    return await call_next(request)


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    # Covers our HTTPExceptions and the framework's own 404/405 for bad routes.
    return error_response(exc.status_code, str(exc.detail), headers=exc.headers)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    errors = [
        {
            # ("body", "company") -> "company"; ("header", "idempotency-key") stays prefixed.
            "field": ".".join(str(part) for part in err["loc"] if part != "body"),
            "message": err["msg"].removeprefix("Value error, "),
        }
        for err in exc.errors()
    ]
    summary = "; ".join(f"{e['field']}: {e['message']}" for e in errors)
    return error_response(422, summary or "Invalid request.", errors=errors)


@app.exception_handler(Exception)
async def unhandled_error(request: Request, exc: Exception):
    # Log the real error for us; never send internals (or secrets) to the client.
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "Internal server error")


app.include_router(resumes.router)
app.include_router(applications.router)
app.include_router(tailoring.router)

@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
