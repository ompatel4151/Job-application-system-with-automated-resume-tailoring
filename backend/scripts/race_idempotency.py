"""Fire N concurrent identical creates at a running backend, with and without
one shared Idempotency-Key, and count how many records each produced.

The unit tests send their two requests one after another; this checks real
concurrency against a real database. Run against the local Postgres setup
(milestone 6), with RATE_LIMIT_ENABLED=false.

Usage (from backend/): ../.venv/bin/python scripts/race_idempotency.py
"""

import asyncio
import uuid
from collections import Counter

import httpx

BASE = "http://127.0.0.1:8000"
N = 20


async def burst(client: httpx.AsyncClient, company: str, key: str | None):
    headers = {"Idempotency-Key": key} if key else {}
    body = {"company": company, "role": "Race test"}
    responses = await asyncio.gather(
        *(client.post("/api/applications", json=body, headers=headers) for _ in range(N))
    )
    outcomes = Counter(
        f"{r.status_code}{' replayed' if r.headers.get('Idempotent-Replayed') else ''}"
        for r in responses
    )
    rows = [a for a in (await client.get("/api/applications")).json() if a["company"] == company]
    return outcomes, len(rows)


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30) as client:
        tag = uuid.uuid4().hex[:8]
        for label, key in (("without a key", None), ("with one shared key", f"race-{tag}")):
            outcomes, rows = await burst(client, f"Race {tag} {label}", key)
            print(f"{N} concurrent creates {label}: responses {dict(outcomes)} -> {rows} record(s)")


if __name__ == "__main__":
    asyncio.run(main())
