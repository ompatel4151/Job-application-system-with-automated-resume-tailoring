# Results

Real measurements only. Each entry states the command, the machine and the
commit. Anything not measured is marked "not measured".

## Machine

- Apple M4, 16 GB RAM, macOS 27.0.1
- Python 3.11.15 (project venv)
- Database for tests: in-memory SQLite

## Milestone 1: baseline

**Test suite.** Run once on commit `ce5d48f`:

```bash
cd backend && ../.venv/bin/python -m pytest
```

Output: `55 passed in 0.38s`. That's a single run, so treat the time as
rough. It is not a benchmark.

## Milestone 2: tests first

Suite run once on commit `a256d21`, same machine and command:

Output: `70 passed, 1 xfailed in 0.71s`

- 55 existing tests, plus 15 new contract tests (one of them runs 9 times,
  once per endpoint).
- The 1 xfailed test is audit #4 (`PATCH null` returns 500). It is expected
  to fail until milestone 4.
- Times are single runs and not benchmarks.

## Milestone 3: idempotency

On commit `9117019`, same machine:

- Backend, `cd backend && ../.venv/bin/python -m pytest`:
  `77 passed, 1 xfailed in 0.81s`. That's 7 new idempotency tests; the
  xfail is still audit #4.
- Frontend, `cd frontend && npm test`: `10 passed`. One new test checks the
  `Idempotency-Key` header is sent.
- Before the fix, the same tests ran red: 5 failed, 2 passed. The retried
  create returned a new id (2 instead of 1), and the retried tailor called
  the model twice.

## Milestone 4: validation and errors

On commit `5bfe82b`, same machine:

- Backend: `93 passed in 0.43s`, 0 xfailed. That's 16 new validation tests;
  the audit #4 known-issue test was removed once it started passing.
- Frontend: `10 passed`, lint clean, build OK.
- Before the fix the new tests ran red: 14 failed, 2 passed. Every bad input
  returned 201, `PATCH null` raised the database error again, errors had no
  `code`, and a score of 150 passed through.

## Milestone 5: rate limiting

On commit `b6dd38d`, same machine:

- Backend: `103 passed in 0.51s`. That's 10 new rate-limit tests; the tests
  use a fake clock, so no timing is involved.
- Frontend: `10 passed`, lint clean, build OK.
- Before the code existed, the test file failed to import (`cannot import
  name 'ratelimit'`).
- Check that the security test can fail: I removed the "trust X-Forwarded-For
  only with the API key" condition, and
  `test_spoofed_forwarded_ip_is_ignored_without_the_key` failed (1 failed,
  9 passed). Then I restored the code.
- The limits (5/min for LLM endpoints, 60/min otherwise) are design choices,
  not measurements.

## Milestone 6: load test (local only)

Everything here ran on one laptop. Nothing was deployed and no real traffic
was measured.

### Setup

- **Machine:** Apple M4, 16 GB RAM, macOS 27.0.1.
- **Database:** PostgreSQL 16.15 in Docker (`docker compose up -d db`). The
  Docker VM had 10 CPUs and 7.7 GiB of memory.
- **API:** `uvicorn app.main:app --port 8000`, one process.
  - FastAPI's default thread pool and SQLAlchemy's default connection pool
    (5, overflow 10).
  - `RATE_LIMIT_ENABLED=false`, so the test measures the app, not the
    limiter.
- **Load generator:** `scripts/loadtest.py` (asyncio + httpx), on the **same
  machine**, so it competes with the server for CPU.
- **Data:** `scripts/seed_load.py`. Synthetic and deterministic: 2,000
  applications and 200,000 tailored resumes (100 each). That's far more than
  one real user; it's sized to make query costs visible.
- **Request mix (read-only):**
  - 50% `GET /api/applications/{id}`
  - 25% `GET /api/applications/{id}/tailored`
  - 15% `GET /api/applications/stats`
  - 10% `GET /api/applications`
- **Load:** 20 concurrent clients, 4,000 requests per run, after a
  200-request warmup that isn't counted.
- **Command:**
  `cd backend && ../.venv/bin/python scripts/loadtest.py --requests 4000 --concurrency 20`

### The bottleneck, confirmed before fixing it

The detail endpoint counts tailored resumes by `application_id`, and that
column had no index. One run of `EXPLAIN (ANALYZE, BUFFERS)` for
`SELECT count(id) FROM tailored_resumes WHERE application_id = 7`:

| | Plan | Pages read | Execution time |
|---|---|---|---|
| Before | Parallel Seq Scan (whole table, about 199,900 rows filtered out) | 5,406 | 10.8 ms |
| After | Bitmap Index Scan on `ix_tailored_resumes_application_id` | 101 | 0.35 ms |

### Results, all runs, none dropped

| Run | Throughput | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|
| Before, run 1 | 171 req/s | 117.2 ms | 200.9 ms | 232.0 ms | 0.00% |
| Before, run 2 | 170 req/s | 116.7 ms | 203.2 ms | 240.2 ms | 0.00% |
| After, run 1 | 233 req/s | 85.8 ms | 166.7 ms | 190.8 ms | 0.00% |
| After, run 2 | 230 req/s | 85.0 ms | 175.6 ms | 219.2 ms | 0.00% |

Per endpoint, p50 in ms (before runs 1 and 2 → after runs 1 and 2):

- detail: 114.4, 113.9 → 80.9, 78.7
- tailored list: 118.0, 118.0 → 84.3, 85.6
- stats: 92.7, 96.5 → 80.1, 72.4
- board list: 168.5, 164.4 → 126.8, 130.5

How to read it:

- About 36% more throughput and about 27% lower p50. That's far less than the
  query's own speedup, because the bottleneck moved.
- In every run, p50 is close to concurrency ÷ throughput (Little's law:
  20/171 ≈ 117 ms, 20/233 ≈ 86 ms). So the server stayed saturated, and most
  of the latency is waiting in line.
- After the fix, the remaining cost is **not measured**. My guess is Python
  request handling in a single process plus the load generator sharing the
  CPU.
- The board list (every row, no pagination, audit #11) is still the slowest
  endpoint.
- Two runs each is a small sample. Treat these as one machine's numbers, not
  a benchmark.

### Concurrent idempotency check (real Postgres)

`scripts/race_idempotency.py` sends 20 concurrent identical
`POST /api/applications` requests. Ran 3 times, same result each time:

- Without a key: 20 × 201, **20 records** (the duplicate race from audit #3).
- With one shared key: 1 × 201 and 19 × 201 replayed, **1 record**.

### Migration note

`create_all` builds the index on a **new** database. A fresh re-seed produced
`ix_tailored_resumes_application_id`. It does **not** add the index to an
existing database. The live Supabase database would need this run by hand:

```sql
CREATE INDEX ix_tailored_resumes_application_id ON tailored_resumes (application_id);
```

**Not applied.** Nothing was deployed.

## Milestone 7: final check

On branch `harden/milestone-7-docs`, same machine:

- Backend, `pytest`: `104 passed in 0.47s`.
- Frontend:
  - `npm test`: `10 passed`
  - `npm run lint`: 0 problems
  - `npm run build`: compiled successfully
  - `npx playwright test`: `1 passed`

**Live deployment.** No performance numbers exist. All the hardening was
tested locally only and has never served real traffic. The app was never load
tested, and no latency or traffic was measured. Load testing is milestone 6
and will run **locally only**.
