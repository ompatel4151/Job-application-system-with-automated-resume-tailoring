# Backend image: FastAPI on uvicorn.
FROM python:3.11-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so this layer caches across code changes.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code, and the migrations it runs at startup.
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser
USER appuser

# The host injects PORT (defaults to 8080); listen on it.
ENV PORT=8080
EXPOSE 8080

# --no-access-log: the app writes its own JSON line per request, with the
# request id and route template.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080} --no-access-log"]
