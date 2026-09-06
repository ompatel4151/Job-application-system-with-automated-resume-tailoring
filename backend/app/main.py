import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.exc import OperationalError

from app.config import settings
from app.database import Base, engine
from app.routers import applications, resumes, tailoring

logger = logging.getLogger(__name__)

CREATE_RETRIES = 5
RETRY_DELAY_SECONDS = 2


def init_db(retries: int = CREATE_RETRIES, delay: float = RETRY_DELAY_SECONDS) -> None:
    """Create tables, tolerating a database that is still waking up.

    Managed Postgres instances can refuse the first connection after a cold
    start; without the retry a transient blip takes the whole app down at boot.
    """
    for attempt in range(1, retries + 1):
        try:
            Base.metadata.create_all(bind=engine)
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
    "job description with Claude.",
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


@app.middleware("http")
async def require_api_key(request: Request, call_next):
    """Gate /api routes behind a shared key when one is configured.

    Disabled entirely when API_KEY is unset, so local dev and the test suite
    stay open. Preflight OPTIONS requests are never gated, or CORS would break.
    """
    if (
        settings.api_key
        and request.url.path.startswith("/api")
        and request.method != "OPTIONS"
        and request.headers.get("x-api-key") != settings.api_key
    ):
        return JSONResponse({"detail": "Invalid or missing API key."}, status_code=401)
    return await call_next(request)


app.include_router(resumes.router)
app.include_router(applications.router)
app.include_router(tailoring.router)

STATIC_DIR = Path(__file__).parent / "static"


@app.get("/", include_in_schema=False)
def dashboard():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/health", tags=["meta"])
def health():
    return {"status": "ok"}
