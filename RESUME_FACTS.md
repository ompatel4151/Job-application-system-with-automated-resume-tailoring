# Resume facts

Every fact here comes from a command that was actually run. Each one gives the
command, where it ran, and the sizes. Anything not measured says so. Earlier
measurements (hardening milestones 1 to 7) are in [RESULTS.md](RESULTS.md).

Machine for anything marked **local**: Apple M4, 16 GB, macOS, Docker 29.7.2,
Python 3.11.15, `postgres:16-alpine` in Docker.

## Item 1: migrations (Alembic)

| Fact | Where | How |
|---|---|---|
| The baseline migration builds the same schema as the old `create_all`. Apart from the `alembic_version` table and RLS being on, the `pg_dump --schema-only` output is identical. | local | Built one database with `Base.metadata.create_all` and one with `migrate()`, ran `pg_dump --schema-only --no-owner` on both, then `diff`. |
| The live Supabase schema matches the baseline: the same 28 columns (type, length, nullability), 7 constraints, enum labels and FK index. | live (read-only queries) | Queried `information_schema.columns`, `pg_constraint`, `pg_enum` and `pg_indexes` on both databases and compared. |
| 2 backend containers started at the same moment on an empty database both came up healthy, and the database ended at revision `0001`. | local | 2 containers of the production image against one Postgres, with the advisory lock in `migrations/env.py`. 1 run. |
| A database built by `create_all` (with no `alembic_version`) was adopted at startup. It was stamped `0001` and serves requests. | local | A 3rd container pointed at the `create_all` database. 1 run. |
| The drift test fails when a model column has no migration. | local | Mutation check: added a column to `Application`, ran `tests/test_migrations.py` (it failed with `add_column ... salary`), then restored the file. |
| Tests: 7 new migration tests (3 on SQLite, 4 on Postgres). Full suite: 112 passed with Postgres available. | local | `TEST_POSTGRES_URL=... pytest` |

Not measured: how long migrations take on the live database (no live deploy of
this yet).

## Item 2: accounts (Supabase Auth, RLS)

| Fact | Where | How |
|---|---|---|
| Every `/api` endpoint returns 401 without a valid token. Tested cases: no token, garbage, Basic auth, expired, wrong audience, wrong issuer, missing or non-UUID `sub`, a token signed by another key, and `alg: none`. | local | `tests/test_auth.py` (parametrized), SQLite |
| The backend fetches the live project's real ES256 public key (JWKS) and rejects a token forged with the real key id, with `InvalidSignatureError`. | local backend, live Supabase JWKS | A one-off script calling `app.auth` with `SUPABASE_URL` set to the project. 1 run. |
| User B gets 404 on every one of user A's rows, across the get, patch, put, delete, tailor, tailored-list and markdown endpoints, and B's lists and stats are empty. | local | `tests/test_auth.py`, SQLite |
| On Postgres, with RLS and no `WHERE` clause, a user sees only their own rows. Updating or deleting another user's rows affects 0 rows, and inserting a row for another user fails with "row-level security". | local, Postgres 16 | `tests/test_rls.py` |
| **Defense in depth, shown by a mutation check.** With the `user_id` filter deleted from the list query, the SQLite API tests failed (2 tests), but the Postgres API test still passed, because RLS blocked the leak on its own. It failed only once the per-request role switch was also turned off. | local | Edited the code, ran `test_auth.py` and `test_rls.py`, then restored from a copy. 1 run each. |
| Changing the policy to `USING (true)` made 4 of the 5 RLS tests fail. | local, Postgres 16 | Mutation check, restored from a copy. |
| Tests: backend 137 passed with Postgres (128 run without it). Frontend: 10 Vitest tests and 3 Playwright tests. | local | `TEST_POSTGRES_URL=... pytest`, `npm test`, `E2E_PORT=3107 npm run test:e2e` |

Not tested: a real sign-up or sign-in against Supabase. That needs an account
on a remote service, which only you can create. The browser flow from login
to API call is untested end to end until you sign in on the deployed site.

## Item 3: cursor pagination

| Fact | Where | How |
|---|---|---|
| Walking 120 rows 25 at a time gives 5 pages, with every row exactly once and in order. 30 rows with an identical timestamp, 7 per page, are neither skipped nor repeated. | local | `tests/test_pagination.py`, SQLite |
| Mutation check: dropping the `id` tie-breaker from the cursor comparison made the identical-timestamp test fail. | local | Edited `app/pagination.py`, ran the tests, restored from a copy. |
| On 200,000 applications (20,000 owned by one user), a cursor page about 5,000 rows deep read **9 shared buffers and 51 rows** (index scan backward on `ix_applications_user_updated`), in **0.09 to 0.12 ms**. The same page by `OFFSET 5000` read **685 buffers and 5,051 rows**, in **1.15 to 1.60 ms**. | local, Postgres 16 | `EXPLAIN (ANALYZE, BUFFERS)`, 3 timing runs each, synthetic data from `generate_series`. Query plan time only, not an HTTP measurement. |
| Tests: backend 149 passed with Postgres (140 without it). Frontend: 14 Vitest tests and 3 Playwright tests. | local | `pytest`, `npm test`, `E2E_PORT=3107 npm run test:e2e` |

## Item 4: shared rate limits (Redis, Lua)

| Fact | Where | How |
|---|---|---|
| 2 separate app processes on one Redis: 10 LLM-endpoint calls alternating between them gave **5 allowed and 5 × 429**, so the limit is 5 a minute in total. | local, Redis 7 in Docker | `tests/test_redis_ratelimit.py`. Real uvicorn processes, real token verification against a local JWKS. |
| The control, the same 2 processes without Redis, gave **0 × 429** for the same 10 calls (each process allowed 5 on its own). | local | Same test file. |
| 50 concurrent takes on a 10-token bucket: exactly 10 allowed. | local, Redis 7 | `asyncio.gather` of 50 `take()` calls. |
| Mutation check: replacing the Lua script with a separate read then write let **50 of 50** through, in 5 of 5 runs. | local | Edited `app/ratelimit.py`, ran the test 5 times, restored from a copy. |
| With Redis unreachable, a request is allowed (fails open). | local | Pointed the bucket at a closed port. |

| Tests: backend 155 passed with Postgres and Redis (140 without them). | local | `TEST_POSTGRES_URL=... TEST_REDIS_URL=... pytest` |

Not measured: latency added per request against a hosted Redis (Upstash).

## Item 5: observability

| Fact | Where | How |
|---|---|---|
| A request id goes from the Next.js proxy to the backend and back to the browser. A missing or malformed id (not a UUID, 500 characters long, or containing a newline) is replaced with a new one. | local | `tests/test_observability.py`, `route.test.ts` |
| One JSON log line per request, with the route template, status, duration and user id. No token appears in any log record. | local | Same tests, plus the production image's container log |
| Metrics are labelled by route template. In the production image, a request refused with 401 before routing was still counted as `/api/applications/{application_id}`. | local, Docker | `curl /metrics` against the image, 1 run |
| Mutation check: labelling by raw path instead of route template made 2 tests fail. | local | Edited `app/main.py`, ran the tests, restored from a copy |
| `/metrics` returns 401 without the API key, and also when no key is configured. | local | Tests, plus `curl` against the image |
| Tests: backend 171 passed with Postgres and Redis (156 without them). Frontend: 16 Vitest tests and 3 Playwright tests. | local | `pytest`, `npm test`, `npm run test:e2e` |

Not measured: overhead added by the logging and metrics per request (see the
load-test re-run at the end). Nothing scrapes the metrics yet.

## Load test re-run (local only), old code vs new code

Same machine and setup as milestone 6 in RESULTS.md:

- Apple M4, 16 GB, macOS 27.0.1, PostgreSQL 16.15 in Docker.
- 1 uvicorn process, `RATE_LIMIT_ENABLED=false`.
- Synthetic data: 2,000 applications and 200,000 tailored resumes.
- 20 concurrent clients, 4,000 requests after a 200-request warmup.
- The load generator runs on the same machine.

Old = `main` at `15008c7`. New = the end of item 5. Both ran in the same
session, against their own copy of the same seeded data. New requests carry a
real ES256 token, verified against a local JWKS (`scripts/dev_jwks.py`),
with RLS on. All runs are shown; none were dropped.

**Full request mix** (50% detail, 25% tailored list, 15% stats, 10% board list):

| Run | Throughput | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|
| Old, run 1 | 232 req/s | 85.9 ms | 167.0 ms | 197.5 ms | 0% |
| Old, run 2 | 232 req/s | 86.7 ms | 165.0 ms | 188.3 ms | 0% |
| New, run 1 | 574 req/s | 29.2 ms | 72.5 ms | 149.3 ms | 0% |
| New, run 2 | 597 req/s | 29.9 ms | 65.8 ms | 72.9 ms | 0% |

**This is not the same workload.** In the new code the board list returns 50
rows instead of all 2,000, and the tailored list returns 50 instead of 100.
The server is saturated (p50 is close to 20 ÷ throughput, by Little's law),
so cheaper list responses shorten the queue for every endpoint. Don't quote
this as "2.5x faster". It is the effect of pagination on this mix.

**Single-row endpoints only** (`--no-lists`: detail and stats, which
pagination didn't change), both run with `--no-access-log`. This isolates the
per-request cost of auth, RLS, JSON logging and metrics:

| Run | Throughput | p50 | p95 | p99 |
|---|---|---|---|---|
| Old, run 1 | 552 req/s | 20.2 ms | 110.8 ms | 178.1 ms |
| Old, run 2 | 548 req/s | 20.8 ms | 108.9 ms | 174.4 ms |
| New, run 1 | 602 req/s | 23.1 ms | 102.2 ms | 172.9 ms |
| New, run 2 | 544 req/s | 20.7 ms | 115.7 ms | 179.6 ms |

The difference is within the run-to-run spread (544 to 602 req/s for the
same code). With 2 runs each, the honest conclusion is "no overhead
measurable on this setup", not "no overhead".

Commands: `scripts/seed_load.py`, `scripts/dev_jwks.py`, then
`scripts/loadtest.py --requests 4000 --concurrency 20 --token "$TOKEN"`,
optionally with `--no-lists`.

Not measured:

- Redis-backed rate limiting under load. Redis was off in these runs, the
  same as before.
- Any live or AWS latency.

## Item 6: AWS (Terraform), on hold

| Fact | Where | How |
|---|---|---|
| The Terraform config is formatted and valid against AWS provider v5.100.0. | local | `terraform fmt -check` and `terraform validate` (Terraform 1.9.8 in Docker) |

**Not done, so nothing to claim yet:** no `plan` against a real account, no
`apply`, no running service, no AWS latency or cost. The ~$40/month figure in
infra/README.md is an estimate from public price lists, not a bill.

## Live deploy of items 1 to 5 (2026-10-19, main at `a3537a3`)

| Fact | Where | How |
|---|---|---|
| CI passed on `main`, including the Postgres, Redis and Terraform jobs. The AWS deploy workflow was skipped, as designed. | GitHub Actions | `gh run list --branch main` |
| The live database migrated itself on deploy: it is at revision `0002`, all 4 tables have `user_id`, and each has the `own_rows` policy. No manual steps. | live Supabase (read-only query) | `alembic_version`, `pg_policies`, `information_schema.columns` |
| Signed out, the live site redirects `/` to `/login` (307), and the API through the site returns 401 "Sign in to continue." | live | `curl` |
| The backend called directly, without the proxy's key, returns 401 "Invalid or missing API key." | live | `curl` |

Not yet verified live: a real sign-up, sign-in and use of the app (needs your
account), and shared rate limits (only if `REDIS_URL` is set on Render).

## PDF export and ATS check

| Fact | Where | How |
|---|---|---|
| The generated PDF reads back as text: name, contact, every section heading, every bullet. A short resume is 1 page. | local | `tests/test_pdf.py`, extracting the text with pypdf |
| The ATS check is deterministic: the same resume and keywords give an identical report. A strong sample scores 100/100, with points summing to 100. | local | `tests/test_ats.py` |
| Mutation check: comparing without the plain-character swap failed the curly-quote test. Skipping the real PDF and comparing against the source text failed 3 tests. | local | Edited `app/services/ats.py`, ran the tests, restored from a copy |
| Adding fpdf2 grew the backend image from 462 MB to 537 MB (it brings in Pillow and fonttools). | local, Docker | `docker images` |
| Tests: backend 187 passed with Postgres and Redis. Frontend: 18 Vitest tests and 7 Playwright tests. | local | `pytest`, `npm test`, `npm run test:e2e` |

Not measured: how any real ATS product scores these PDFs. The check is a
readiness heuristic, not a prediction.

## Current totals (2026-10-19, main at `ef2d8cc`)

| Fact | Where | How |
|---|---|---|
| 218 automated tests: 193 backend (pytest; 1 SQLite-only test skipped), 18 frontend unit (Vitest), 7 end-to-end (Playwright). | local, with Postgres 16 and Redis 7 in Docker | `TEST_POSTGRES_URL=... TEST_REDIS_URL=... pytest`, `npm test`, `npm run test:e2e` |
| 92% backend line coverage (1,193 statements, 94 missed). | local, same run | `pytest --cov=app` |
| 18 API endpoints under `/api` (plus `/health` and `/metrics`). | local | Counted from the OpenAPI schema |
| Live bugs found and fixed after deploy: sign-in buttons that never submitted (Base UI defaults to `type="button"`); PDF titles running into the dates; 43 non-breaking hyphens and 19 narrow spaces printing as "?"; an ATS keyword count (5 of 19) that contradicted the AI's lists. Each fix shipped with a regression test. | live, then local tests | Reproduced from the live PDF and the Render request logs |

## Agent experiment, Step 1: baseline (plain mode), branch `experiment/grounded-agent`

These numbers are for the existing one-call tailoring, measured before any agent
code exists. They're on 30 synthetic job descriptions, not real postings or
users. Full table and caveats: AGENT_EXPERIMENT.md, section 10.

| Fact | Where | How |
|---|---|---|
| 90 tailorings (30 synthetic JDs × 3 runs): 90 succeeded; 1 needed a re-run after a Groq `json_validate_failed`. | my Mac, free-tier Groq, `openai/gpt-oss-120b`, 2026-10-26 to 2026-10-27 | `eval/run_eval.py --mode plain --version v0 --run 1/2/3` |
| Invented-fact rate (bullets the checker or the judge found unsupported by my fact sheet): median 32.7% across 3 runs (range 29.0% to 35.2%). Checker alone: 2.0%; judge alone: 32.5%. **Not yet validated against my hand labels**, so not a headline number yet. | same, judge `qwen/qwen3.8-27b` | `eval/score.py --mode plain --version v0` |
| Mean ATS score: 79.9 over 90 tailorings, against frozen per-JD keywords. | same | same |
| Latency: pooled p50 5.78 s, p95 9.45 s (90 tailorings, network to Groq included). | same | same, after amendment A3 |
| Cost: 1 LLM call and about 4,878 tokens per tailoring, about $0.0018 at list price (the free tier billed $0). | same | token counts from the API, prices from `eval/prices.json` |
| A measurement bug found and fixed: the OpenAI SDK's silent retries put a 600 s timeout into two latency samples (604.7 s, 704.1 s). The harness now retries outside the timer and re-measured them (6.1 s, 6.7 s); both versions are reported. | same | amendment A3 |

Not measured yet: the agent (Step 2 isn't built), hand-label agreement (rule 6),
any comparison between the two.
