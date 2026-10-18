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
- **Web dashboard.** A zero-build single-page dashboard served by the API,
  plus interactive OpenAPI docs at `/docs`.

## Architecture

Two services in one repo. The browser talks only to the Next.js frontend, which
proxies API calls server-side to the FastAPI backend (attaching the API key), so
the key never reaches the browser and there is no CORS to manage.

```
backend/                 # FastAPI service
├── app/
│   ├── main.py          # app, router wiring, CORS, API-key gate
│   ├── config.py        # environment-based settings
│   ├── database.py      # SQLAlchemy engine / session
│   ├── models.py        # ORM: Resume, Application, TailoredResume
│   ├── schemas.py       # Pydantic request/response schemas
│   ├── routers/         # applications, resumes, tailoring
│   ├── services/        # tailoring + upload extraction (Claude / Groq)
│   └── static/          # legacy vanilla-JS dashboard (still served at /)
├── tests/               # pytest suite (API + service layer, model mocked)
└── Dockerfile
frontend/                # Next.js App Router (TypeScript, Tailwind, shadcn/ui)
├── src/app/             # board, application detail, tailor, base-resume pages
│   └── api/[...path]/   # server-side proxy to the backend
├── src/lib/api/         # OpenAPI-generated types, typed client, Query hooks
├── e2e/                 # Playwright smoke test
└── Dockerfile
docker-compose.yml       # db + backend + frontend for local dev
.github/workflows/       # CI (tests) and Deploy (Cloud Run)
```

**Backend:** Python 3.11 · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite or
Postgres · Anthropic and OpenAI SDKs · pypdf · pytest
**Frontend:** Next.js · React · TypeScript · Tailwind · TanStack Query ·
Vitest · Playwright
**Infra:** Docker · GitHub Actions · Cloud Run · Supabase Postgres

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
`GROQ_API_KEY` (free) in your shell or a `.env` file before bringing it up. To
require a key on the API, set `API_KEY` too and it is applied to both services.

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

The frontend tests cover the status config, the API client (including the
`Idempotency-Key` header) and the board rendering. CI runs all of these on
every pull request.

## API overview

| Method | Endpoint | Purpose |
|---|---|---|
| `GET/POST` | `/api/applications` | List (filterable by status) / create |
| `GET/PATCH/DELETE` | `/api/applications/{id}` | Read / update / delete |
| `GET` | `/api/applications/stats` | Pipeline counts |
| `GET/POST` | `/api/resumes` | List / create base resumes |
| `POST` | `/api/resumes/parse` | Parse an uploaded PDF or image into resume content |
| `GET/PUT/DELETE` | `/api/resumes/{id}` | Read / update / delete |
| `POST` | `/api/applications/{id}/tailor` | Generate a tailored resume |
| `GET` | `/api/applications/{id}/tailored` | List tailored versions |
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

**Requests are rate-limited** per client with token buckets: 5 per minute
for the two LLM endpoints and 60 per minute for everything else, in separate
buckets. Over the limit you get a 429 with `Retry-After`.

- Behind the frontend proxy, set `TRUST_FORWARDED_FOR=true` so each visitor
  is limited separately. The forwarded IP is only trusted on requests that
  carry the API key.
- Limits live in memory, so they are per server process and reset on
  restart.

**Indexed for the detail page.** `tailored_resumes.application_id` is
indexed. Postgres doesn't index foreign keys on its own.

- In a local load test on a synthetic 200,000-row dataset, throughput went
  from about 170 to about 230 requests/s.
- That's one machine, with client and server sharing the CPU. Full setup and
  every run are in RESULTS.md.
- Reproduce it with `scripts/seed_load.py` and `scripts/loadtest.py`.
- `create_all` doesn't add indexes to an existing database, so an existing
  database needs the `CREATE INDEX` statement from RESULTS.md.

**Known limitations.**

- There are no user accounts. Anyone who can load the frontend can use the
  whole API through its proxy (AUDIT #1). Rate limiting reduces the damage;
  real auth is the fix.
- Rate limits aren't shared across servers.
- There are no schema migrations.
- List endpoints aren't paginated. The full board list is now the slowest
  endpoint in the load test.

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

## Roadmap

- [ ] PDF export (rendered from the Markdown)
- [ ] Cover letter generation using the same match analysis
- [ ] Job description scraping from a URL
- [ ] Reminders / follow-up nudges for stale applications
- [ ] Auth + multi-user support
- [x] Hosted deployment
