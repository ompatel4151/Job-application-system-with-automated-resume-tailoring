"""Cursor ("keyset") pagination for list endpoints.

A page is the next `limit` rows after the last row the client saw, in a fixed
order: the sort column descending, then id descending as a tie-breaker. The
cursor is that last row's (sort value, id), base64-encoded. Unlike OFFSET, the
database seeks straight to the cursor using the (user_id, sort, id) index, so
page 100 costs the same as page 1, and inserting a row doesn't shift pages.
"""

import base64
import json
from datetime import datetime
from typing import Annotated

from fastapi import HTTPException, Query
from sqlalchemy import tuple_

DEFAULT_LIMIT = 50
MAX_LIMIT = 100

Limit = Annotated[int, Query(ge=1, le=MAX_LIMIT)]
Cursor = Annotated[str | None, Query(max_length=200)]


def encode(at: datetime, row_id: int) -> str:
    raw = json.dumps([at.isoformat(), row_id]).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(cursor: str) -> tuple[datetime, int]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        at, row_id = json.loads(base64.urlsafe_b64decode(padded))
        return datetime.fromisoformat(at), int(row_id)
    except (ValueError, TypeError):
        # Same shape as any other 422, so the client handles it the same way.
        raise HTTPException(422, "Invalid cursor. Start again without one.") from None


def paginate(query, sort_col, id_col, limit: int, cursor: str | None):
    """One page of `query`, and the cursor for the next page (None at the end)."""
    if cursor is not None:
        at, row_id = decode(cursor)
        query = query.filter(tuple_(sort_col, id_col) < tuple_(at, row_id))
    # One extra row says whether another page exists, without a COUNT.
    rows = query.order_by(sort_col.desc(), id_col.desc()).limit(limit + 1).all()
    if len(rows) <= limit:
        return rows, None
    last = rows[limit - 1]
    return rows[:limit], encode(getattr(last, sort_col.key), last.id)
