"""Idempotency-Key support for create endpoints.

A client sends a unique Idempotency-Key header with a create request. The
first request with that key does the work and stores its response. A retry
with the same key gets the stored response back, instead of creating a second
record or paying for a second LLM call.

It all happens inside the request's single database transaction: insert the
key row, do the work, save the response, commit once. The key is the table's
primary key, so two requests with the same key can't both insert it. The
second one gets an IntegrityError and replays what the first one stored. If
the request fails, nothing is committed, so the key stays free to retry.
"""

import hashlib
import json
from typing import Annotated

from fastapi import Header, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models

REPLAY_HEADER = "Idempotent-Replayed"

# The optional header, shared by every endpoint that supports it.
IdempotencyKeyHeader = Annotated[str | None, Header(max_length=255)]


def fingerprint(method: str, path: str, body: dict) -> str:
    """A hash that identifies the request, so a reused key can be detected."""
    raw = json.dumps([method, path, body], sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()


def claim(
    db: Session, user_id, key: str | None, method: str, path: str, body: dict
) -> tuple[models.IdempotencyKey | None, JSONResponse | None]:
    """Reserve `key` for this request, or return the stored response for a retry.

    Keys are per user: the same key from two users is two separate requests.
    Returns (row, None) when the caller should do the work and then `save`,
    (None, response) when this is a retry and `response` should be returned,
    and (None, None) when no key was sent.
    Call it before the endpoint writes anything: on a conflict it rolls back.
    """
    if key is None:
        return None, None

    fp = fingerprint(method, path, body)
    row = models.IdempotencyKey(user_id=user_id, key=key, fingerprint=fp)
    db.add(row)
    try:
        db.flush()  # INSERT now, so a duplicate key fails here, before any work
        return row, None
    except IntegrityError:
        db.rollback()

    existing = db.get(models.IdempotencyKey, (user_id, key))
    if existing is None:
        # The other request holding this key failed and rolled back meanwhile.
        raise HTTPException(409, "A request with this Idempotency-Key is in progress. Retry.")
    if existing.fingerprint != fp:
        raise HTTPException(
            422, "This Idempotency-Key was already used for a different request."
        )
    return None, JSONResponse(
        existing.response_body,
        status_code=existing.status_code,
        headers={REPLAY_HEADER: "true"},
    )


def save(row: models.IdempotencyKey | None, status_code: int, body: dict) -> None:
    """Record the response; it commits together with the record it describes."""
    if row is not None:
        row.status_code = status_code
        row.response_body = body
