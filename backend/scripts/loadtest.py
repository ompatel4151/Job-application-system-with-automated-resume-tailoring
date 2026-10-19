"""Small load test for a locally running backend (milestone 6).

Sends a fixed, read-only request mix from N concurrent clients and prints
throughput, p50/p95/p99 latency and error rate, overall and per endpoint.

It measures one machine: the load generator, the API server and the database
(in Docker) all share the same CPU, so the absolute numbers are only
comparable to other runs on the same setup.

Every request sends --token as a bearer token (see scripts/dev_jwks.py).

Usage (from backend/, with the API running on :8000):
  ../.venv/bin/python scripts/loadtest.py --requests 4000 --concurrency 20 --token "$TOKEN"
"""

import argparse
import asyncio
import random
import statistics
import time
from collections import defaultdict

import httpx

APPLICATIONS = 2_000  # must match scripts/seed_load.py

# (label, weight, path). Roughly one board visit: open some detail pages, view
# tailored versions, refresh the stats and the board.
MIX = [
    ("GET /api/applications/{id}", 50, lambda r: f"/api/applications/{r.randint(1, APPLICATIONS)}"),
    ("GET /api/applications/{id}/tailored", 25,
     lambda r: f"/api/applications/{r.randint(1, APPLICATIONS)}/tailored"),
    ("GET /api/applications/stats", 15, lambda r: "/api/applications/stats"),
    ("GET /api/applications", 10, lambda r: "/api/applications"),
]


LIST_LABELS = {"GET /api/applications/{id}/tailored", "GET /api/applications"}


def percentiles(ms: list[float]) -> tuple[float, float, float]:
    q = statistics.quantiles(ms, n=100)  # 99 cut points
    return q[49], q[94], q[98]


async def run(base: str, total: int, concurrency: int, seed: int, token: str | None, mix=MIX):
    results: list[tuple[str, float, int]] = []  # (label, ms, status; 0 = exception)
    remaining = total
    labels = [m[0] for m in mix]
    weights = [m[1] for m in mix]
    builders = {m[0]: m[2] for m in mix}

    async with httpx.AsyncClient(
        base_url=base,
        timeout=30,
        limits=httpx.Limits(max_connections=concurrency),
        headers={"Authorization": f"Bearer {token}"} if token else None,
    ) as client:

        async def worker(worker_id: int):
            nonlocal remaining
            rng = random.Random(seed * 1000 + worker_id)  # same mix every run
            while remaining > 0:
                remaining -= 1
                label = rng.choices(labels, weights)[0]
                path = builders[label](rng)
                start = time.perf_counter()
                try:
                    status = (await client.get(path)).status_code
                except httpx.HTTPError:
                    status = 0
                results.append((label, (time.perf_counter() - start) * 1000, status))

        started = time.perf_counter()
        await asyncio.gather(*(worker(i) for i in range(concurrency)))
        elapsed = time.perf_counter() - started
    return results, elapsed


def report(results, elapsed, mix=MIX):
    def row(name, rows):
        ms = [r[1] for r in rows]
        errors = sum(1 for r in rows if r[2] == 0 or r[2] >= 400)
        p50, p95, p99 = percentiles(ms)
        return (f"| {name} | {len(rows)} | {p50:.1f} | {p95:.1f} | {p99:.1f} "
                f"| {100 * errors / len(rows):.2f}% |")

    print(f"Requests: {len(results)} in {elapsed:.2f}s = {len(results) / elapsed:.0f} req/s")
    print("| Endpoint | Requests | p50 ms | p95 ms | p99 ms | Errors |")
    print("|---|---|---|---|---|---|")
    print(row("**All**", results))
    by_label = defaultdict(list)
    for r in results:
        by_label[r[0]].append(r)
    for label, *_ in mix:
        print(row(label, by_label[label]))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--base", default="http://127.0.0.1:8000")
    p.add_argument("--requests", type=int, default=4000)
    p.add_argument("--concurrency", type=int, default=20)
    p.add_argument("--warmup", type=int, default=200)
    p.add_argument("--seed", type=int, default=1)
    p.add_argument("--token", help="bearer token; required since accounts were added")
    # Only the single-row endpoints, whose response size pagination didn't
    # change: isolates per-request overhead (auth, RLS, logging).
    p.add_argument("--no-lists", action="store_true")
    a = p.parse_args()

    mix = [m for m in MIX if not (a.no_lists and m[0] in LIST_LABELS)]
    asyncio.run(run(a.base, a.warmup, a.concurrency, 99, a.token, mix))  # not recorded
    results, elapsed = asyncio.run(run(a.base, a.requests, a.concurrency, a.seed, a.token, mix))
    print(f"Concurrency: {a.concurrency}, warmup: {a.warmup} requests (not counted)")
    report(results, elapsed, mix)


if __name__ == "__main__":
    main()
