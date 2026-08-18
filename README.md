# Job Application Tracker with AI Resume Tailoring

**Live demo:** https://job-application-tracker-d3me.onrender.com
· [API docs](https://job-application-tracker-d3me.onrender.com/docs)

> Hosted on Render's free tier, so the first request after a period of
> inactivity takes about 30 to 60 seconds while the instance wakes up.

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

```
app/
├── main.py              # FastAPI app, router wiring, static dashboard
├── config.py            # environment-based settings
├── database.py          # SQLAlchemy engine / session management
├── models.py            # ORM models: Resume, Application, TailoredResume
├── schemas.py           # Pydantic request/response schemas
├── routers/
│   ├── applications.py  # CRUD + status pipeline + stats
│   ├── resumes.py       # base resume CRUD, single-default enforcement
│   └── tailoring.py     # tailoring endpoints + markdown export
├── services/
│   ├── tailoring.py     # LLM tailoring (Claude / Groq, structured outputs)
│   └── extraction.py    # parse uploaded PDFs and images into resume content
└── static/index.html    # dashboard UI (vanilla JS, no build step)
tests/                   # pytest suite (API + service layer, model mocked)
```

**Stack:** Python 3.11 · FastAPI · SQLAlchemy 2.0 · Pydantic v2 · SQLite or
Postgres · Anthropic and OpenAI SDKs · pypdf · pytest

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

```bash
git clone <this repo>
cd Job-application-system-with-automated-resume-tailoring
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env      # add an API key (see "Tailoring backend" below)

uvicorn app.main:app --reload
```

Open <http://localhost:8000> for the dashboard, or
<http://localhost:8000/docs> for the interactive API docs.

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

```bash
pytest
```

The suite covers the application pipeline, resume management (including
single-default enforcement), the upload and tailoring flows with the model
call mocked, and the Markdown renderer.

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

## Deployment

Deployed on Render with Postgres on Supabase. Step-by-step instructions,
including the Supabase pooler gotcha, are in [DEPLOY.md](DEPLOY.md).

## Roadmap

- [ ] PDF export (rendered from the Markdown)
- [ ] Cover letter generation using the same match analysis
- [ ] Job description scraping from a URL
- [ ] Reminders / follow-up nudges for stale applications
- [ ] Auth + multi-user support
- [x] Hosted deployment
