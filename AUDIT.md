# Backend audit (milestone 1)

Scope: the FastAPI backend in `backend/`, plus the Next.js proxy route that
forwards to it. Audited on branch `harden/milestone-1-audit`, starting from
commit `ce5d48f`.

Every finding is marked with how it was established:

- **Verified**: reproduced by running code. Re-run with
  `cd backend && PYTHONPATH=. ../.venv/bin/python scripts/audit_probe.py`
  (uses an in-memory SQLite database, touches nothing real).
- **Read**: found by reading the code. Not reproduced.

## What exists today

**Stack.** Python 3.11, FastAPI, SQLAlchemy 2.0, Pydantic v2. SQLite locally,
Postgres (Supabase) in production. LLM calls go through the Anthropic SDK
(Claude) or the OpenAI SDK pointed at Groq.

**Endpoints (16 operations).**

| Area | Endpoints |
|---|---|
| Applications | `POST /api/applications`, `GET /api/applications?status=`, `GET /api/applications/stats`, `GET/PATCH/DELETE /api/applications/{id}` |
| Resumes | `POST /api/resumes`, `POST /api/resumes/parse` (upload, calls an LLM), `GET /api/resumes`, `GET/PUT/DELETE /api/resumes/{id}` |
| Tailoring | `POST /api/applications/{id}/tailor` (calls an LLM), `GET /api/applications/{id}/tailored`, `GET /api/tailored/{id}`, `GET /api/tailored/{id}/markdown` |

Plus `GET /health` and `GET /` (legacy dashboard page).

**Data model.** Three tables: `resumes`, `applications`, `tailored_resumes`
(foreign keys to both, cascade delete). No explicit indexes, no unique
constraints. Tables are created at startup with `create_all`; there are no
migrations.

**Access control.** One shared API key. When `API_KEY` is set, a middleware
requires it in the `X-API-Key` header on `/api` routes. There are no users.

**Tests.** 55 pytest tests across 7 files, all passing (see RESULTS.md). The
LLM is mocked in every test.

## Findings, ranked

Severity = how bad the realistic worst case is, times how easy it is to
trigger.

| # | Severity | Finding | Evidence |
|---|---|---|---|
| 1 | Critical | The public frontend lets anyone use the whole API | Read |
| 2 | High | Paid LLM endpoints have no limits at all | Read + Verified |
| 3 | High | Retried creates make duplicate records | Verified |
| 4 | High | `PATCH` with `null` on a required field returns 500 | Verified |
| 5 | Medium | Weak input validation | Verified |
| 6 | Medium | Error responses have inconsistent shapes | Verified |
| 7 | Medium | Two resumes can both end up as "default" | Read |
| 8 | Low | API key check fails open and isn't constant-time | Read |
| 9 | Low | Upload size limit is checked after the body is received | Read |
| 10 | Low | No indexes on filtered, sorted and joined columns | Read |
| 11 | Low | No pagination on list endpoints | Read |
| 12 | Low | No migrations, so schema changes won't reach the live DB | Read |
| 13 | Info | Secrets: none in code; one key should be rotated | Read + checked git history |
| 14 | Info | Test gaps | Read |

### 1. Critical: the public frontend lets anyone use the whole API

`frontend/src/app/api/[...path]/route.ts` forwards **every** method (GET,
POST, PUT, PATCH, DELETE) for **any** path under `/api`, and attaches the
secret API key to every request. So the key only protects the backend's own
URL. Anyone who can load the Vercel site can, through its `/api` routes,
create, edit and delete every record and trigger paid LLM calls, without
knowing the key.

During the September deployment, records were created and deleted through
the Vercel `/api` URL without sending a key, which confirms the path works.
Not re-run today: the live backend has not been responding since early
October.

Real fix: user authentication. Rate limiting (milestone 5) reduces the
damage but does not fix who is allowed to do what.

### 2. High: paid LLM endpoints have no limits at all

`POST /api/applications/{id}/tailor` and `POST /api/resumes/parse` each make
a paid LLM call. Neither has:

- **Rate limiting.** Nothing stops a loop of calls.
- **Idempotency.** A retried tailor request makes a second LLM call and saves
  a second row.
- **A size cap on the input.** A 2,000,000-character `job_description` was
  accepted (probe #6), and tailoring would send all of it to the model.
- **An explicit timeout.** No timeout is configured, so the SDK defaults
  apply. Checked on the installed versions (anthropic 0.122.0, openai 3.0.0):
  read timeout 600 seconds per attempt, and 2 automatic retries.

Also, the database session stays open for the whole LLM call, because
`get_db` holds it for the entire request. Combined with finding 1, a stranger
could spend your LLM budget.

### 3. High: retried creates make duplicate records

There is no idempotency key and no unique constraint. Sending the same
`POST /api/applications` body twice created two rows (probe #1). A
double-click or a network retry does the same. This applies to
`POST /api/resumes` and the tailor endpoint too.

### 4. High (bug): `PATCH` with `null` on a required field returns 500

`PATCH /api/applications/{id}` with `{"company": null}` returned **500
Internal Server Error** (probe #5). Every field in `ApplicationUpdate` is
optional, so an explicit `null` passes validation. Then the code writes
`None` into a `NOT NULL` column and the commit fails with an unhandled
`IntegrityError`. The client should get a 422 instead.

### 5. Medium: weak input validation

All verified with the probe:

- Empty `company` and `role` are accepted (probe #2).
- No length limits in the schemas. A 300-character `company` was accepted on
  SQLite (probe #3). The column is `VARCHAR(200)`, so Postgres would most
  likely reject it with an unhandled database error. **Not tested on
  Postgres.**
- `job_url` isn't validated: `javascript:alert(1)` was stored (probe #4).
  The React frontend should block `javascript:` links when it renders them,
  but the API shouldn't store them in the first place.
- `job_description`, `notes` and resume content have no size limit (probe #6).
- `match_score` is described as 0 to 100, but nothing enforces that range.

### 6. Medium: error responses have inconsistent shapes

- 404 / 400: `{"detail": "a string"}`
- 422: `{"detail": [ ... ]}`, a list of objects (probe #7)
- 401 from the middleware: `{"detail": "..."}`
- Unhandled errors: a plain-text `Internal Server Error` body (probe #5)

A client has to handle four different shapes. There is no global error
handler.

### 7. Medium: two resumes can both end up as "default"

To set a default, the code first un-sets the old default and then sets the
new one, in two separate steps. Nothing in the database enforces "at most one
default", for example a partial unique index. Two simultaneous "make default"
requests could leave two defaults. The tailoring code even guards against
this case ("if data ever ends up with more than one default"). Not
reproduced: SQLite serializes writes, so it is hard to trigger locally.

### 8. Low: API key check fails open and isn't constant-time

- If `API_KEY` is missing in production, the API silently becomes fully open.
  That is fail-open: a lost environment variable means no protection, with no
  error.
- The key is compared with `!=`, not `hmac.compare_digest`. Comparison time
  can in theory leak how much of a guess is correct. Low practical risk over
  a network, but a one-line fix.

### 9. Low: upload size limit is checked after the body is received

`_read_capped` claims to reject oversized uploads "without pulling the whole
thing into memory first". But FastAPI/Starlette parses the full multipart
body (writing large files to a temporary file) **before** the endpoint runs,
so the whole upload is received before the check happens. There is no
server-level limit on request size. Based on how Starlette handles uploads;
**not measured**.

### 10. Low: no indexes on filtered, sorted and joined columns

The list endpoint filters on `applications.status` and sorts by
`updated_at`. The counts query groups by `tailored_resumes.application_id`.
Postgres doesn't index foreign keys automatically, and none of these columns
has an index. **Impact not measured**; at current data size it is probably
irrelevant. Milestone 6 will measure it.

### 11. Low: no pagination on list endpoints

All list endpoints return every row.

### 12. Low: no migrations, so schema changes won't reach the live DB

`create_all` only creates **missing** tables. It never alters existing ones.
Any unique constraint or index added in later milestones would not reach an
existing Postgres database without a migration or a manual change. This
matters for milestones 3 and 6.

### 13. Info: secrets

- No real secrets in tracked files. The only credentials are placeholders and
  the local-only `app:app` login for the docker-compose Postgres.
- `.env` files are gitignored.
- The production API key does not appear anywhere in git history (checked
  with `git log --all -S`).
- That key **was pasted into AI chat sessions** during deployment.
  Recommendation: rotate it.

### 14. Info: test gaps

None of the 55 tests covers: duplicate creates, `null` in a `PATCH`,
oversized or empty input, concurrency, the proxy forwarding everything, or
rate limits.

## Context, not a code finding

As of 2026-10-07, the live Render backend was not responding. The most likely
cause is the free Supabase project pausing after inactivity, which makes
startup fail. Not investigated further. This milestone deploys nothing.

**Note:** merging any branch into `main` triggers automatic Vercel and Render
deploys. To keep "nothing deployed", this work stays on branches until you
decide otherwise.

## Status after milestones 2 to 6 (updated for the limits work)

Re-running `scripts/audit_probe.py` on the hardened code: probes 2 to 6 now
return 422 instead of 201 or 500, and errors carry a `code`. Probe 1 still
creates 2 rows on purpose, because it sends no `Idempotency-Key` and keyless
requests behave as before.

| # | Finding | Status |
|---|---|---|
| 1 | Open proxy | **Fixed** (limits item 2). Every `/api` request needs a verified Supabase token; rows are scoped per user in queries and by RLS. Sign-up is open, so anyone can still make an account. |
| 2 | LLM endpoints unlimited | **Mostly fixed.** Rate limit 5/min (M5), idempotent retries (M3), 20k job description cap (M4). **Still open:** no explicit LLM timeout (SDK default 600s), and the DB session is held during the call. |
| 3 | Duplicate creates | **Fixed for clients that send a key** (M3); the frontend does. 20 concurrent keyed creates gave 1 record on Postgres (M6). Keyless requests still duplicate, by design. |
| 4 | `PATCH null` returns 500 | **Fixed** (M4), now 422. |
| 5 | Weak validation | **Fixed** for applications and resume names (M4). Resume *content* is still unbounded, deliberately: the same schema is the LLM's output schema. |
| 6 | Inconsistent errors | **Fixed** (M4): `{detail, code}` everywhere. |
| 7 | Two default resumes | **Open.** |
| 8 | API key fails open, `!=` compare | **Fixed** (M5, limits item 2). Constant-time compare. The API key is now a second check; the user token is required and fails closed if `SUPABASE_URL` is unset. |
| 9 | Upload size checked after receipt | **Open.** |
| 10 | Missing indexes | **Fixed for `tailored_resumes.application_id`** (M6, measured). `applications.status` and `updated_at` not indexed; not measured to matter. |
| 11 | No pagination | **Open.** The full board list is now the slowest endpoint in the M6 load test. |
| 12 | No migrations | **Fixed** (limits item 1). Alembic; the live database matched the baseline and is adopted automatically. |
| 13 | Rotate the API key | **Open.** Your action. |
| 14 | Test gaps | **Fixed** (M2 to M6): 55 tests became 104 backend tests. |

## Mapping to the planned milestones

| Milestone | Addresses |
|---|---|
| 2: tests first | 14, plus a failing test for one finding (suggested: #4) |
| 3: idempotency | 3, and part of 2 |
| 4: validation and errors | 4, 5, 6 |
| 5: rate limiting | 2, and part of 1 |
| 6: load test and index | 10 |
| Not planned | 1 (needs auth), 7, 8, 9, 11, 12, 13 |
