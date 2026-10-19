# Job Application Tracker with AI Resume Tailoring

**Live demo:** https://job-application-system-with-automat-rosy.vercel.app
· [API docs](https://job-tracker-backend-cm7h.onrender.com/docs)

> The frontend is on Vercel (instant); the backend is on Render's free tier, so
> the first data load after a period of inactivity takes about 30 to 60 seconds
> while the backend wakes up.

A full-stack web application for managing a job search end to end: track every
application through a status pipeline, store structured base resumes, and
generate a **resume tailored to each specific job description** with an LLM,
returning a match score, matched and missing keywords, and concrete
recommendations.

## Features

- **Application pipeline.** Track applications through
  `saved → applied → screening → interview → offer / rejected`, with automatic
  timestamping of when you applied and live pipeline statistics.
- **Structured resumes.** Resumes are stored as structured JSON (summary,
  skills, experience, projects, education) rather than opaque text, so they can
  be programmatically rewritten and rendered.
- **Resume upload.** Drop in a PDF, JPEG, PNG, or WebP and it gets parsed into
  that structure for review before saving. Text PDFs are read locally with
  pypdf so no vision tokens are spent; scans and photos fall back to a
  multimodal model.
- **AI resume tailoring.** One click sends your base resume plus the job
  description to the model, which rewrites bullet points to mirror the job's
  vocabulary, reorders skills by relevance, and trims irrelevant content, all
  under a strict "never invent experience" system prompt. Structured outputs
  guarantee the response always matches the resume schema.
- **Match analysis.** Every tailored resume comes with a 0 to 100 fit score,
  the keywords you match, the requirements you're missing, and specific
  recommendations (what to learn, what to address in a cover letter).
- **Markdown export.** Download any tailored resume as a Markdown document,
  ready to convert to PDF.
- **Accounts.** Sign in with email and password (Supabase Auth). Each user only
  ever sees their own applications and resumes.
- **API docs.** Interactive OpenAPI docs at `/docs` on the backend.

## Architecture

Two services in one repo. The browser talks only to the Next.js frontend, which
proxies API calls server-side to the FastAPI backend, attaching the API key and
the signed-in user's access token. Neither reaches client-side code, and there
is no CORS to manage.

```
backend/                 # FastAPI service
├── app/
│   ├── main.py          # app, router wiring, CORS, auth and rate-limit middleware
│   ├── auth.py          # verifies Supabase access tokens (ES256, JWKS)
│   ├── observability.py # request ids, JSON logs, Prometheus metrics
│   ├── config.py        # environment-based settings
│   ├── database.py      # engine, sessions (run as the user for RLS), migrate()
│   ├── models.py        # ORM: Resume, Application, TailoredResume
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── routers/         # applications, resumes, tailoring
│   └── services/        # tailoring + upload extraction (Claude / Groq)
├── migrations/          # Alembic migrations
├── tests/               # pytest suite (API + service layer, model mocked)
└── Dockerfile
frontend/                # Next.js App Router (TypeScript, Tailwind, shadcn/ui)
├── src/app/             # board, application detail, tailor, base-resume, login
│   └── api/[...path]/   # server-side proxy to the backend
├── src/proxy.ts         # refreshes the session, sends signed-out visitors to /login
├── src/lib/api/         # OpenAPI-generated types, typed client, Query hooks
├── e2e/                 # Playwright smoke tests
└── Dockerfile
docker-compose.yml       # db + backend + frontend for local dev
.github/workflows/       # CI (tests, Terraform checks), AWS deploy (off until set up)
infra/                   # Terraform for AWS (validated, not applied)
```

**Backend:** Python 3.11 · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite or
Postgres · Anthropic and OpenAI SDKs · pypdf · pytest
**Frontend:** Next.js · React · TypeScript · Tailwind · TanStack Query ·
Vitest · Playwright
**Infra:** Docker · GitHub Actions · Vercel · Render · Supabase (Postgres, Auth)

Key design decisions:

- **Structured outputs, not prompt-and-pray.** The tailoring call validates the
  model's response against a Pydantic schema, so it always matches the exact
  resume shape instead of parsing free text by hand. On Claude this uses the
  Anthropic SDK's `messages.parse()`; on Groq it uses a strict JSON schema.
- **The LLM layer is isolated.** All model interaction lives in one service
  module behind a plain function, so the API layer is fully testable with the
  model mocked, and the provider can be swapped in one place.
- **Honesty guardrails in the prompt.** The system prompt forbids inventing
  employers, titles, dates, or metrics. Tailoring means rephrasing and
  reordering, not fabricating.

## Getting started

The fastest path runs the whole stack (Postgres, backend, frontend) in
containers:

```bash
docker compose up --build
```

Then open <http://localhost:3000> for the app. Tailoring needs an LLM key; set
`GROQ_API_KEY` (free) in your shell or a `.env` file before bringing it up.
Signing in needs a Supabase project: set `SUPABASE_URL` and
`SUPABASE_PUBLISHABLE_KEY` (Project Settings, then API Keys). To require a key
between proxy and API, set `API_KEY` too and it is applied to both services.

### Running the services directly

Backend:

```bash
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # add an API key (see "Tailoring backend" below)
uvicorn app.main:app --reload --port 8000
```

Frontend (in another terminal):

```bash
cd frontend
npm install
cp .env.example .env.local   # BACKEND_URL defaults to http://localhost:8000
npm run dev
```

Open <http://localhost:3000> for the app, or <http://localhost:8000/docs> for
the interactive API docs. Use `localhost`, not `127.0.0.1`, in dev.

### Tailoring backend

Tailoring runs against either provider behind a single interface, both using
schema-constrained structured outputs so the response is always valid against
the resume schema:

| Provider | Env var | Notes |
|---|---|---|
| Claude | `ANTHROPIC_API_KEY` | Default. Uses the Anthropic SDK's `messages.parse`. |
| Groq | `GROQ_API_KEY` | OpenAI-compatible; free tier, no card required. |

Set one key and it is used automatically; set both and Claude wins. Force a
choice with `LLM_PROVIDER=claude` or `LLM_PROVIDER=groq`.

On Groq, only the `openai/gpt-oss-*` models support strict schemas, so
`GROQ_MODEL` defaults to `openai/gpt-oss-120b`. Groq's free tier also has a
small per-minute token budget, and a single tailoring call can use most of it,
so on the free tier expect roughly one request per minute before hitting a
rate limit.

Uploading a resume image needs vision, which `gpt-oss` does not have, so that
path uses `GROQ_VISION_MODEL` (default `qwen/qwen3.6-27b`) with best-effort
JSON validated against the schema. Claude reads PDFs and images natively, so it
is the better choice for scanned resumes, since Groq cannot read a PDF that has
no text layer.

### Typical workflow

1. Add your base resume (structured JSON) and mark it default.
2. Add an application with the job description pasted in.
3. Click **Tailor resume** and review the match score and tailored bullets.
4. Download the Markdown, update the application status as you progress.

## Running tests

Backend:

```bash
cd backend && pytest
```

The migration tests also run against Postgres when `TEST_POSTGRES_URL` is set
(CI sets it; locally they skip):

```bash
docker run -d --name pg -e POSTGRES_PASSWORD=pg -p 55432:5432 postgres:16-alpine
TEST_POSTGRES_URL=postgresql://postgres:pg@localhost:55432/postgres pytest
```

Frontend:

```bash
cd frontend
npm run lint
npm test          # Vitest unit tests
npm run test:e2e  # Playwright smoke test
```

The backend suite covers:

- the application pipeline and resume management (including the single
  default resume)
- the upload and tailoring flows, with the model call mocked
- the API-key gate and the Markdown renderer
- contract tests that pin response shapes and status codes
- idempotency, input validation and rate limiting
- migrations: they build exactly the models' schema, round-trip down and
  up, and adopt a database built before migrations existed

The frontend tests cover the status config, the API client (including the
`Idempotency-Key` header) and the board rendering. CI runs all of these on
every pull request.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET/POST` | `/api/applications` | List (paginated, filterable by status) / create |
| `GET/PATCH/DELETE` | `/api/applications/{id}` | Read / update / delete |
| `GET` | `/api/applications/stats` | Pipeline counts |
| `GET/POST` | `/api/resumes` | List (paginated) / create base resumes |
| `POST` | `/api/resumes/parse` | Parse an uploaded PDF or image into resume content |
| `GET/PUT/DELETE` | `/api/resumes/{id}` | Read / update / delete |
| `POST` | `/api/applications/{id}/tailor` | Generate a tailored resume |
| `GET` | `/api/applications/{id}/tailored` | List tailored versions (paginated) |
| `GET` | `/api/tailored/{id}/markdown` | Download as Markdown |

## Reliability and safety

These were added in a hardening pass. [AUDIT.md](AUDIT.md) lists every
weakness found and its status, and [RESULTS.md](RESULTS.md) has the
measurements. All of it was tested **locally only**; none of it has run
against real traffic.

**Retries are safe.** `POST /api/applications`, `POST /api/resumes` and the
tailor endpoint accept an optional `Idempotency-Key` header.

- The first request with a key does the work and stores the response.
- A retry with the same key gets that stored response back, marked
  `Idempotent-Replayed: true`, instead of creating a duplicate or paying for
  a second LLM call.
- Reusing a key for a different request returns 422.
- The key is a primary key, so even concurrent duplicates create exactly one
  record (checked with 20 concurrent requests against Postgres).
- The frontend sends a key with each create and reuses it on retry.

**Bad input is rejected early.** Names must be non-empty and at most 200
characters, matching the database columns. Job links must be `http(s)`. Job
descriptions are capped at 20,000 characters, since they're sent to the LLM.
Every error has the same shape:

```json
{"detail": "company: String should have at least 1 character", "code": "validation_error",
 "errors": [{"field": "company", "message": "String should have at least 1 character"}]}
```

`detail` is always a readable string and `code` is machine-readable. Only
422s include `errors`. Unexpected failures return a generic 500 and are
logged; internals aren't sent to the client.

**Every request is signed in, and users are kept apart twice.**

- The backend verifies the Supabase access token on every `/api` request: its
  ES256 signature against the project's published keys, expiry, audience and
  issuer. Without a valid one it returns 401. If `SUPABASE_URL` is unset,
  every `/api` request is refused rather than left open.
- Every query is filtered by the caller's user id. Someone else's row returns
  404, the same as a row that doesn't exist.
- Row-level security is the second layer. The backend runs each transaction
  as Supabase's `authenticated` role with the caller's id, so a policy
  (`user_id = auth.uid()`) filters every table even if a query forgot its
  filter. A test that deletes a filter shows the policy still holding.
- Idempotency keys are per user, so one user's key can't replay another
  user's stored response.

**Requests are rate-limited** per user with token buckets: 5 per minute
for the two LLM endpoints and 60 per minute for everything else, in separate
buckets. Over the limit you get a 429 with `Retry-After`.

- With `REDIS_URL` set, the buckets live in Redis and every instance spends
  from the same one. One Lua script does the refill and the spend, so two
  instances can't both take the last token. Redis's clock is used, not each
  instance's. A test starts 2 app processes on one Redis and gets exactly 5
  LLM calls through, not 10.
- If Redis is unreachable the limiter fails open: requests are allowed and an
  error is logged, so an outage doesn't take the app down, but limits stop
  working until Redis is back.
- Without `REDIS_URL` (local dev), buckets live in memory, per process.

**Indexed for the detail page.** `tailored_resumes.application_id` is
indexed. Postgres doesn't index foreign keys on its own.

- In a local load test on a synthetic 200,000-row dataset, throughput went
  from about 170 to about 230 requests/s.
- That's one machine, with client and server sharing the CPU. Full setup and
  every run are in RESULTS.md.
- Reproduce it with `scripts/seed_load.py` and `scripts/loadtest.py`.
- The index is part of the baseline migration (see Schema migrations below).

**Lists are paginated with cursors.** `GET /api/applications`,
`/api/resumes` and `/api/applications/{id}/tailored` return
`{"items": [...], "next_cursor": "..."}`. Pass `?cursor=` for the next page,
and `?limit=` for the page size (default 50, max 100).

- The cursor is the last row's (sort value, id). The next page seeks past it
  through the `(user_id, sort, id)` index instead of counting rows with
  `OFFSET`, so a deep page costs the same as the first. On 200,000 synthetic
  rows a page about 5,000 rows deep read 9 buffers against 685 for `OFFSET`
  (RESUME_FACTS.md).
- The board sorts by last update, so moving a card while pages are loading
  can show it twice. The frontend drops the duplicate by id.

**Observable.** See [RUNBOOK.md](RUNBOOK.md) for the three likely failures.

- Every request gets an `X-Request-ID`. The Next.js proxy creates it, the
  backend uses it, and it's returned to the browser. Both sides log one JSON
  line per request with that id, so a request can be followed from the Vercel
  logs to the Render logs. Tokens, headers and bodies are never logged.
- `GET /metrics` serves Prometheus metrics: requests by route template and
  status, a latency histogram, 4xx and 5xx counts, rate-limit rejections by
  bucket, LLM call latency by provider, and Redis errors. It needs the
  `API_KEY`, and is closed if none is set.
- Labels use route templates (`/api/applications/{application_id}`), never raw
  paths, so the number of time series stays fixed.

**Schema migrations.** The schema is managed by Alembic
(`backend/migrations/`). The app runs `alembic upgrade head` at startup, with
the same retry as before for a database that is still waking up.

- A Postgres advisory lock lets only one instance migrate at a time, so
  several instances can start together.
- A database built by the old `create_all` (the live one) has no
  `alembic_version` table. It's stamped as the baseline instead of having its
  tables created again. Its schema was compared with the baseline column by
  column before relying on this.
- New schema change: edit `app/models.py`, then from `backend/` run
  `alembic revision --autogenerate -m "what changed"` and review the file. The
  drift test fails if a model change has no migration.

**Known limitations.**

- The backend runs only on Render. The AWS Terraform is validated but has
  never been applied, so nothing about it has been tested against real AWS.
- One instance with no autoscaling, on Render's free tier, which sleeps when
  idle.

- Nothing scrapes `/metrics` on a schedule, so there are no dashboards or
  alerts yet. A free hosted Prometheus (such as Grafana Cloud's free tier)
  could scrape it.

- Sign-up is open, so anyone can make an account and spend up to 5 LLM calls
  a minute. Requests without a valid token aren't rate-limited, but they're
  refused before any database or LLM work.
- Each rate-limit check is a round trip to Redis. Its latency against a
  hosted Redis (Upstash) hasn't been measured.

## Deployment

The two services deploy to the platform each suits best, both on free plans:

- **Frontend on Vercel:** native Next.js hosting, no cold start.
- **Backend on Render:** a Docker web service ([`render.yaml`](render.yaml)),
  built from `backend/Dockerfile`, with Postgres on Supabase.

The browser only ever talks to the Vercel frontend, which proxies API calls
server-side to the Render backend (attaching `BACKEND_API_KEY`), so the split
needs no CORS and the key never reaches the browser.

- **CI** ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) runs backend
  and frontend tests on every pull request.
- **Deploy:** both platforms auto-deploy on push to `main` once connected.

To deploy: create the Render backend (New > Web Service, Root Directory
`backend`, Docker, Free) with `DATABASE_URL`, `API_KEY`, and `GROQ_API_KEY`;
then import the repo on Vercel with Root Directory `frontend` and set
`BACKEND_URL` to the Render URL and `BACKEND_API_KEY` to the same value as the
backend's `API_KEY`. [TEARDOWN.md](TEARDOWN.md) covers removal and cost (free,
so $0). The earlier single-service setup is in [DEPLOY.md](DEPLOY.md).

**AWS (written, not deployed).** [`infra/`](infra/) has Terraform for the
backend on AWS: ECR, ECS Fargate, an HTTPS load balancer, CloudWatch logs,
Secrets Manager, and a GitHub OIDC deploy role. A budget alert gets applied
first. [`deploy-aws.yml`](.github/workflows/deploy-aws.yml) builds, pushes and
rolls out on merge once it's turned on. CI checks the Terraform with
`fmt` and `validate`. It has **never been applied**, because it costs about
$40 a month; [infra/README.md](infra/README.md) has the estimate, free
alternatives and the steps.

## Roadmap

- [ ] PDF export (rendered from the Markdown)
- [ ] Cover letter generation using the same match analysis
- [ ] Job description scraping from a URL
- [ ] Reminders / follow-up nudges for stale applications
- [ ] Auth + multi-user support
- [x] Hosted deployment
