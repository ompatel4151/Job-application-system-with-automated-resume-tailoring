# Runbook

What to do when the app breaks. These are the three failures most likely to
happen, two of which already have.

## Before anything: follow one request

Every response has an `X-Request-ID` header (open the browser's dev tools,
Network tab, click the failing call). The same id is in:

- the Vercel function logs, as a JSON line from the proxy:
  `{"request_id": "...", "route": "/api/applications", "status": 502, ...}`
- the backend logs on Render, as a JSON line from `app.request`, plus any
  error logged while handling that request

Search both for the id.

Metrics, if you need numbers (needs the backend `API_KEY`):

```bash
curl -s -H "X-API-Key: $API_KEY" https://<backend>/metrics | grep -E "http_errors_total|rate_limit|llm_call"
```

Nothing scrapes these on a schedule yet, so they only show totals since the
last restart.

## 1. Supabase is paused or unreachable

**Has happened:** twice. The free tier pauses a project after about a week
with no activity.

**Symptoms.**

- The board shows "Could not load applications" and the API returns 500s. The
  backend log has `OperationalError` (connection refused or timed out).
- At startup: `Database not ready (attempt n/5)`, then the service crashes
  after the 5th attempt.
- Every request returns 401 "Your session is invalid or has expired". This
  happens when the backend can't fetch Supabase's signing keys (JWKS).

**Check.** Supabase dashboard: is the project status "Paused" or "Inactive"?

**Fix.**

1. Restore the project from the dashboard. It takes a few minutes.
2. Redeploy or restart the Render service, so startup runs again and the
   migrations are checked.
3. Nothing is lost while the project is paused.

**Prevent.** Any request at least once a week keeps the project awake.

## 2. The LLM provider fails or is rate-limited

**Symptoms.** Tailor or resume upload returns 502 with code
`upstream_error`, and the message names the provider, for example
"Groq rate limit reached..." or "Anthropic API error (529): ...". On `/metrics`,
`llm_call_duration_seconds` is high, or its count stops rising while
`http_errors_total{status_class="5xx"}` rises.

**Check.**

1. The provider's status page.
2. On Groq's free tier, the per-minute token budget: one tailoring call can
   use most of it, so two in a row can fail.
3. The model name. Groq retires models, and a retired model fails every call.

**Fix.**

- If it's rate limiting: wait a minute and retry. The frontend reuses the
  same `Idempotency-Key`, so a retry never pays twice.
- If it's a retired model: set `GROQ_MODEL` to a current model that supports
  strict JSON schemas (the `gpt-oss` family), then redeploy.
- To switch providers: set `ANTHROPIC_API_KEY` and `LLM_PROVIDER=claude`.

Everything other than tailoring and upload keeps working throughout.

## 3. A deploy crashes at startup

**Has happened:** once. In October 2026, SQLAlchemy 2.1 changed its default
Postgres driver, and startup failed with `ModuleNotFoundError: psycopg`.

**Symptoms.** Render shows the deploy failing or restarting in a loop, and
the old version keeps serving if it was healthy.

**Check.** The first error in the Render deploy log. Likely causes:

| Log says | Cause | Fix |
|---|---|---|
| `ModuleNotFoundError` | A dependency changed under an unpinned version | Reproduce locally with a fresh `pip install -r requirements.txt`; pin or fix |
| `... has N rows with no owner` | Migration 0002 found rows that existed before accounts | Assign each row a `user_id`, or delete them, then redeploy |
| `relation ... already exists` | A database that has tables but no `alembic_version`, and doesn't match the baseline | Compare it with the baseline schema before stamping anything |
| `Sign-in is not configured` on every call | `SUPABASE_URL` missing | Set it on Render and redeploy |

**Roll back.** In Render, open the service, then Events, and redeploy the
last good commit. Check first whether that commit understands the current
schema:

- Code from after migration 0002 (accounts) runs fine against the same or a
  newer schema.
- Code from **before** 0002 does not. It inserts rows without a `user_id`,
  which the schema now rejects. Fix forward instead. `alembic downgrade 0001`
  would let the old code run, but it drops every row's owner, so don't use it
  on real data.
