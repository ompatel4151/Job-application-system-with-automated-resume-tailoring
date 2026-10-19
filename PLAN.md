# Plan: closing the 6 known limits

Status: **approved 2026-10-18, all recommended options.** Paid items are on
hold (the AWS deploy and a domain); free alternatives are listed under item 6.

Changes from the draft, found while building:

- Item 1: migrations run inside the app's startup (with the existing retry),
  not as a separate step. A Postgres advisory lock serializes concurrent
  instances, so AWS needs no one-off migration task either. A database without
  `alembic_version` is stamped as baseline automatically, so the live database
  needs no manual `alembic stamp`. Safe because its schema was compared with
  the baseline first (RESUME_FACTS.md).

## What I read

Every backend module, router and test, the frontend client, hooks, pages and
proxy, `ci.yml`, `render.yaml`, `docker-compose.yml`, the Dockerfiles, the
load-test scripts, README, AUDIT, RESULTS and TEARDOWN.

I also ran one read-only query against the live Supabase database
(`job-application-tracker`):

| Fact | Why it matters |
|---|---|
| 4 tables, RLS **on**, **no policies** | The backend connects as the table owner, which bypasses RLS. Today RLS only blocks Supabase's public Data API. |
| `ix_tailored_resumes_application_id` exists | The live schema already matches the models, so a baseline migration can be stamped instead of run. |
| No `alembic_version` table | The baseline has to be stamped by hand once. |
| **0 rows** in every table | Adding a `NOT NULL user_id` column needs no backfill. This is the biggest risk-reducer in the whole plan. |
| Postgres 17 (CI and local use 16) | No feature used here differs between them. |

## Decisions I need from you before starting

Each one has a recommendation. Reply with the numbers you want changed, or
"all recommended".

1. **Sign-in method.** Recommended: email + password through Supabase Auth.
   Magic links on Supabase's free built-in email are limited to a few emails
   per hour. GitHub OAuth means setting up an OAuth app first.
2. **Who can sign up.** Recommended: open sign-up, with the LLM rate limit
   applied per user. Recruiters can then try the app. The alternative is to
   create your account and then turn sign-ups off.
3. **How strictly RLS is enforced.** Recommended: **B**.
   - A: the backend keeps connecting as the owner. The per-user filter in
     Python is the real check, and RLS only covers the Data API.
   - B: each request runs `SET LOCAL ROLE authenticated` with the caller's JWT
     claims. If a query ever forgets the `user_id` filter, Postgres still
     blocks it. This is about 20 more lines, plus grants.
4. **The old HTML dashboard at the backend's `/`** (`backend/app/static/index.html`).
   It can't sign in, so it breaks once auth is on. Recommended: delete it. The
   Next.js app replaces it.
5. **Sort key for pagination.**
   - Recommended: keep the current order (applications by `updated_at` desc,
     then `id`).
   - Catch: moving a card changes its `updated_at`, so while pages are loading
     it can show up twice or be skipped. The client removes duplicates by `id`.
   - Sorting by `id` instead would be perfectly stable, but it changes the
     board's order, and the brief says don't change features.
6. **Redis hosting.** Recommended: Upstash free tier. It supports `EVAL` (Lua),
   which the atomic script needs. ElastiCache's smallest node costs money every
   hour.
7. **HTTPS in front of the AWS load balancer.** This one matters. Without a
   certificate, Vercel would send the API key and every user's JWT to the load
   balancer over plain HTTP, across the internet.
   - Recommended: a cheap domain plus a free ACM certificate. The domain costs
     roughly $10-15 a year (not verified).
   - Alternative: put CloudFront in front, which gives an HTTPS
     `*.cloudfront.net` URL. That's more Terraform, and the hop from CloudFront
     to the load balancer is still HTTP unless it also has a certificate.
   - I won't ship HTTP-only to production.
8. **AWS spend.** This conflicts with your earlier rule of "no paid services".
   - See item 6 for a rough estimate. Before any `apply`, I'll give you the
     exact `terraform plan` and a priced estimate.
   - Also decide whether AWS stays running after it's verified, or gets torn
     down (Render stays either way).

**Things only you can do** (I can't create accounts or enter credentials):

- Create the AWS account.
- Install the Terraform CLI and AWS CLI, and run `aws configure` yourself.
- Create the Upstash database.
- Set the Supabase Auth URLs in the dashboard.
- Add the new environment variables in Vercel and Render.

## Order and branches

As you asked, one item per branch and PR, each green before the next starts:

| Order | Branch |
|---|---|
| 1 | `limits/1-migrations` |
| 2 | `limits/2-auth` |
| 3 | `limits/3-pagination` |
| 4 | `limits/4-redis-ratelimit` |
| 5 | `limits/5-observability` |
| 6 | `limits/6-aws` |

Every PR follows the same steps:

1. Write the failing test.
2. Implement.
3. Break the code on purpose to check the key test fails. I'll restore from a
   copy, not with `git checkout`, so uncommitted work can't be lost.
4. Run the full suite, then ask you before merging.

New CI job: a **Postgres 16 service container**. Migrations, the RLS tests and
the two-instance Redis test need the real thing. The current SQLite unit tests
stay as they are, because they're fast.

---

## 1. Migrations (Alembic)

**New dependency:** `alembic`. It's the standard migration tool for
SQLAlchemy, and the stdlib has nothing comparable.

**Files**

- `backend/alembic.ini`, `backend/migrations/env.py` (reads
  `app.database.DATABASE_URL` and `Base.metadata`), and
  `backend/migrations/versions/0001_baseline.py`.
- `backend/app/main.py`: `init_db` stops calling `create_all` in production.
  The SQLite test fixture keeps calling `create_all` directly.
- `backend/Dockerfile`: the start command becomes
  `alembic upgrade head && uvicorn ...`. This is fine on Render, which runs one
  instance. On AWS, migrations run as a separate one-off task (see item 6), so
  two tasks never migrate at the same time.
- `.github/workflows/ci.yml`: a new `migrations` job on Postgres 16.
- `backend/requirements.txt`, README.

**Approach**

- Autogenerate the baseline from the models, then edit it by hand:
  - name the enum type `applicationstatus` explicitly
  - keep the FK index
  - add `ENABLE ROW LEVEL SECURITY` for the 4 tables, on Postgres only, so the
    baseline matches the live database
- Check the baseline is exact, with a schema diff: on a fresh Postgres,
  `pg_dump --schema-only` after `create_all` vs after `alembic upgrade head`.
  The only expected difference is the `alembic_version` table. I'll also run
  `alembic check`, which reports any model change that has no migration.
- Live database: run `alembic stamp 0001` **before** the merge (with your
  approval). That records the baseline without running it.

**Tests**

- In CI: upgrade from an empty database to head, then downgrade to base, then
  upgrade again.
- `alembic check` must report no drift.
- Mutation check: add a column to a model without a migration, and confirm
  `alembic check` fails.

**Risks to the live deploy**

- **High, if I get the order wrong.** If the new start command reaches Render
  before the live database is stamped, `upgrade head` tries to create tables
  that already exist. Startup then fails and the service goes into a crash
  loop. Mitigation: stamp first, then merge.
- SQLite in local dev: Alembic runs on SQLite too. Later migrations that alter
  columns will use `batch_alter_table`.

## 2. Auth (Supabase Auth, JWT verified by FastAPI)

**New dependencies**

- Backend: `PyJWT[crypto]`. The stdlib can't verify ES256 or RS256 signatures.
- Frontend: `@supabase/supabase-js` and `@supabase/ssr`. These are Supabase's
  official client and its cookie-session helper for Next.js.

**Files**

- `backend/app/auth.py` (new): `current_user` dependency.
  - Reads `Authorization: Bearer <jwt>`.
  - Verifies the signature against the project's JWKS
    (`/auth/v1/.well-known/jwks.json`, cached), plus `exp`,
    `aud=authenticated` and `iss`.
  - Returns the user id (`sub`). Anything invalid gets a 401 in the existing
    error shape.
- `backend/app/config.py`: `supabase_url`. The JWKS URL is derived from it.
- `backend/app/models.py`: `user_id` (UUID, `NOT NULL`, indexed) on resumes,
  applications, tailored_resumes and idempotency_keys.
  - The idempotency primary key becomes `(user_id, key)`. **Without this, user
    B could replay user A's stored response by guessing their key.**
  - No foreign key to `auth.users`, so the schema stays portable and CI doesn't
    need Supabase's `auth` schema.
- `migrations/versions/0002_owners.py`:
  - adds the columns
  - composite indexes `(user_id, updated_at, id)` and `(user_id, created_at, id)`,
    which pagination (item 3) needs
  - per-user RLS policies
- RLS policies:
  - `applications`, `resumes`, `tailored_resumes`: `USING (user_id = auth.uid())`
    and `WITH CHECK (user_id = auth.uid())` for the `authenticated` role.
  - `idempotency_keys`: stays with no policies, so the Data API can never read
    it.
  - Under decision 3B, also grants to `authenticated`, and `database.py` sets
    the role and JWT claims at the start of each transaction.
- All three routers: every query is filtered by `user_id`. A row that belongs
  to someone else returns **404, not 403**, so ids don't reveal which rows
  exist.
  - `_clear_default` only clears the caller's own default resume.
  - Stats only count the caller's rows.
  - Tailoring checks that both the application and the resume belong to the
    caller.
- `backend/app/ratelimit.py`: the bucket key becomes the user id when signed
  in, and the IP otherwise.
- Frontend:
  - Supabase clients in `src/lib/supabase/`.
  - `src/app/login/page.tsx`.
  - A route guard that sends signed-out visitors to `/login`.
  - A sign-out control in the header.
- `route.ts`: reads the session from the cookie on the server and forwards
  `Authorization: Bearer <access token>`. It keeps adding `X-API-Key`, so the
  proxy stays the only way in.
- `backend/app/static/index.html`: deleted, if you agree to decision 4.

**Tests**

- Unit tests (SQLite). The test suite signs JWTs with its own key pair, and
  `conftest` patches the JWKS lookup. The default `client` fixture signs in as
  user A, so the existing 105 tests keep their meaning.
  - No token, expired token, wrong signature, wrong `aud`, or `alg: none`:
    each returns 401.
  - **User A vs user B through the API:** for every endpoint, B gets a 404 on
    A's rows (get, patch, put, delete, tailor, tailored list, markdown).
  - B's list and stats don't include A's rows.
  - B can't tailor A's application using B's own resume, or the other way
    round.
  - The same idempotency key used by A and then by B creates two separate
    records, and neither replays the other's response.
- RLS tests (CI Postgres). `auth.uid()` is stubbed to read
  `request.jwt.claims`, the way Supabase defines it.
  - As `authenticated` with A's claims: `SELECT` shows only A's rows.
  - `UPDATE` and `DELETE` on B's rows affect 0 rows.
  - `INSERT` with B's `user_id` is rejected.
  - Live check: I'll show you a read-only check of the real policies on
    Supabase before calling this done.
- Mutation checks:
  - remove the `user_id` filter from one query (the API test must fail, and
    under 3B so must the RLS-backed test)
  - drop one policy (the RLS test must fail)

**Risks to the live deploy (the highest of the six)**

- After this merge, the live site needs a login. Before merging, these must
  be set:
  - Vercel: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY` (the
    publishable key, which is safe in the browser)
  - Render: `SUPABASE_URL`
  - Supabase dashboard: Site URL and redirect URLs set to the Vercel domain

  If any of these is missing, every request returns 401.
- Supabase's free built-in email has a low sending limit. Confirmation emails
  for open sign-ups can hit it.

## 3. Cursor pagination

**New dependencies:** none. TanStack Query's `useInfiniteQuery` is already
installed.

**Endpoints:** `GET /api/applications`, `GET /api/resumes`,
`GET /api/applications/{id}/tailored`.

**Approach**

- Query parameters: `?limit=` (default 50, max 100; larger is a 422) and
  `?cursor=`.
- The cursor is an opaque base64 string of the last row's
  `(sort_value, id)`. The next page is
  `WHERE (sort_col, id) < (:v, :id) ORDER BY sort_col DESC, id DESC LIMIT n+1`.
  The extra row tells us whether there's a next page, without a `COUNT`.
- The composite indexes from item 2 make this an index range scan. I'll check
  that with `EXPLAIN` and record it.
- Response shape changes from a list to `{items, next_cursor}`.
  - This is a deliberate breaking change, so the contract tests are updated
    in the same PR.
  - Malformed cursors get a 422.
  - The `?status=` filter keeps working alongside the cursor.
- Frontend:
  - regenerate `openapi.json` and `schema.ts`
  - the three hooks become `useInfiniteQuery`
  - the board and lists get a "Load more" button
  - pages are flattened and deduplicated by `id` (see decision 5)

**Tests**

- Walk every page of 120 rows: each row appears exactly once, in order.
- Ties on `updated_at` still have a stable order.
- `limit` above 100 returns 422; a bad cursor returns 422.
- Mutation check: drop the `id` tie-breaker from the `WHERE`, and the "every
  row exactly once" test must fail.
- Frontend: a Vitest test for the hook's `getNextPageParam`, and the
  Playwright mock updated to the new shape.

**Risks:** Vercel and Render deploy at slightly different times, so for a short
window the frontend and backend may expect different shapes. Mitigation: for
this one release, the frontend accepts either a plain array or the new
envelope. That code gets removed in item 5.

## 4. Shared rate limits (Redis + Lua)

**New dependency:** `redis` (redis-py). It's the standard client, and the
stdlib has none.

**Files:** `backend/app/ratelimit.py`, `config.py` (`redis_url`),
`docker-compose.yml` (a local `redis` service), and CI (a Redis service
container).

**Approach**

- One Lua script does the token bucket's read, refill, take and write as one
  atomic `EVALSHA`. The limits stay the same: 5 per minute on the LLM
  endpoints, 60 per minute elsewhere, 429 with `Retry-After`.
- The clock comes from Redis `TIME` inside the script, so app instances whose
  clocks disagree still compute the same refill.
- Each bucket key has a `PEXPIRE` set to its refill time, so idle buckets
  delete themselves. That replaces `MAX_CLIENTS`.
- If `REDIS_URL` is unset (local dev, SQLite tests), the current in-memory
  limiter is used. The algorithm, and its existing 11 tests, stay the same.
- If Redis is unreachable, the limiter **fails open**: the request is allowed,
  an error is logged, and a metric counts it. The alternative, failing closed,
  would make a Redis outage take down the whole app. I'll note this choice in
  RUNBOOK.md.

**Tests**

- The existing 11 tests run against both the in-memory and the Redis limiter.
- New: start **2 uvicorn processes on different ports** against one Redis. Send
  LLM requests to them in turn. Exactly 5 in total must succeed, not 10.
- Concurrency: 50 parallel `take` calls on one key give exactly `capacity`
  successes.
- Mutation check: split the Lua script into a separate `GET` and `SET`. The
  concurrency test must fail. (It's a race, so it might pass by luck; I'll
  record how many runs I tried.)

**Risk:** a wrong `REDIS_URL` on Render. Failing open plus the error log means
it can't take the site down, but limits quietly stop working. The metric from
item 5 makes that visible.

## 5. Observability

**New dependency:** `prometheus-client`. Writing histogram exposition by hand is
possible but easy to get wrong. The structured logs use the stdlib only (a
`logging.Formatter` that writes JSON, plus a `contextvar` for the request ID).

**Files:** `backend/app/observability.py` (new), `main.py`, `route.ts`,
`RUNBOOK.md` (new).

**Approach**

- Request ID:
  - The proxy creates one with `crypto.randomUUID()`, sends it as
    `X-Request-ID`, and logs it.
  - The backend accepts it only if it's a well-formed UUID; otherwise it makes
    its own.
  - The backend returns it as a response header, and the proxy passes that
    header back to the browser.
- One JSON log line per request: request ID, method, route template (not the
  raw path), status, duration, user ID. Request bodies and tokens are never
  logged.
- `/metrics`:
  - `http_requests_total{method,route,status}`
  - `http_request_duration_seconds` histogram
  - 4xx and 5xx counts, derived from the status label
  - `rate_limit_rejections_total{bucket}`
  - `llm_call_duration_seconds{provider,operation}`
  - `ratelimit_redis_errors_total`
- `/metrics` is protected by the API key, so it isn't public.
- **Limitation:** nothing scrapes the metrics yet. That needs a Prometheus
  server or the free tier of a hosted one. I'll write that down rather than
  imply there are dashboards.
- RUNBOOK.md, for the 3 most likely failures:
  1. Supabase is paused or unreachable (this has already happened twice).
  2. The LLM provider is failing or rate-limited (502s, slow
     `llm_call_duration`).
  3. A deploy crashes at startup (the SQLAlchemy 2.1 driver case, or a
     migration that wasn't stamped).

**Tests**

- The request ID is passed through, a bad one is replaced, and it appears in
  both the response header and the log line.
- Counters go up for 200, 404, 429 and 500 responses.
- The histogram records observations.
- `/metrics` returns 401 without the key.
- Mutation check: route labels using raw paths (so every id becomes its own
  label). The cardinality test must fail.

**Risk:** low. Each new metric label costs memory, so labels use route
templates only.

## 6. AWS (Terraform: ECR, ECS Fargate, ALB, CloudWatch, Secrets Manager)

**New tools:** the Terraform CLI and AWS CLI, which you install. Nothing new in
the app.

**Files:** `infra/` (new), `.github/workflows/deploy-aws.yml` (new),
`TEARDOWN.md` (an AWS section added; Render and Vercel sections kept), and
`RUNBOOK.md`.

**Order, inside this item**

1. **The billing alarm comes first**, as its own `terraform apply`:
   - an AWS Budget with an email alert at $10 and $25 (2 budgets are free)
   - a CloudWatch billing alarm in us-east-1

   You'll need to turn on billing alerts in the account settings first.
2. State: an S3 bucket, using Terraform's native S3 lock file. It's created
   once by a small bootstrap step.
3. Infrastructure:
   - **Region** `us-west-1`, the same AWS region as the Supabase project, so
     database queries don't cross regions.
   - **Network:** the default VPC with public subnets. The task gets a public IP
     so it can reach ECR, Supabase and the LLM APIs **without a NAT gateway**.
     A NAT gateway would be the biggest single cost. The task's security group
     only accepts traffic from the load balancer's security group.
   - **ECR** repository, keeping only the last 5 images.
   - **ECS Fargate:** 1 task, the smallest size (0.25 vCPU, 0.5 GB),
     health-checked on `/health`.
   - **ALB** with HTTPS (see decision 7). Port 80 only redirects to 443.
   - **CloudWatch** log group, kept for 7 days.
   - **Secrets Manager:** the secret entries are created by Terraform, but the
     values are set with the AWS CLI, so they never appear in the Terraform
     state file. Secrets: `DATABASE_URL`, `API_KEY`, `GROQ_API_KEY`,
     `REDIS_URL`.
4. Deploy from GitHub Actions on merge to main:
   - Authenticates with **OIDC**, so no long-lived AWS keys are stored in
     GitHub.
   - Builds the image and pushes it to ECR.
   - Runs `alembic upgrade head` as a one-off ECS task.
   - Updates the service and waits until it's stable.
5. Cutover: only after the AWS backend is verified, switch Vercel's
   `BACKEND_URL` to the load balancer (or your domain). Render stays as it is,
   and pointing `BACKEND_URL` back is the rollback.

**Rough monthly cost.** These numbers are **from memory and unverified**. I'll
replace them with a priced estimate before any `apply`:

| Item | Estimate |
|---|---|
| ALB | ~$16-20 plus usage |
| Public IPv4 addresses (load balancer and task) | ~$7-11 |
| Fargate, 0.25 vCPU / 0.5 GB, running all month | ~$9-10 |
| Secrets Manager | ~$0.40 per secret, so ~$1.60 |
| CloudWatch and ECR | under $1 at this volume |
| **Total** | **roughly $35-45 a month** |

Credits on a new AWS account may cover some of it. I haven't checked what your
account would get.

**Tests and verification**

- `terraform fmt -check` and `terraform validate` run in CI. No apply happens in
  CI except through the deploy workflow after merge.
- After the deploy, a smoke script against the load balancer checks:
  - `/health`
  - a 401 without a token
  - one full signed-in round trip (create, list, delete)
  - the 429 burst
  - `/metrics` behind the key

  The results are recorded in RESUME_FACTS.md with "AWS" as the environment.
- TEARDOWN.md: the exact `terraform destroy` order. Service first, then the
  rest, then the state bucket last. It ends with a check that nothing is left
  that could bill.

**Risks:**

- The live site isn't affected until the cutover.
- The real risk is money:
  - the billing alarm comes first
  - I'll show you the plan and wait for approval before each `apply`
  - `destroy` is written down before anything is created

---

## Honesty and measurements

- New `RESUME_FACTS.md`. Every fact gets:
  - the exact command
  - the environment (local, live or AWS)
  - the machine or instance size
  - the client count and number of runs
- The existing RESULTS.md stays as the record of the earlier milestones and is
  linked from it.
- **Load test re-run.** Same machine and script, same data sizes (2,000
  applications, 200,000 tailored resumes), concurrency 20, 4,000 requests after
  200 warmup, 2 runs each. Three changes make it not exactly the same test, and
  I'll write that down:
  - The seeded data has to belong to one user, and requests carry a JWT. The
    JWT check adds work to every request.
  - With Redis, each request makes an extra round trip. I'll run it with rate
    limiting off, the same as before, and separately with the limiter on.
  - `GET /api/applications` now returns 50 rows instead of all 2,000. That
    will make it much faster. I'll report it separately so the overall number
    isn't inflated by it.

  If something got slower, it gets recorded as slower.
- At the end: README "Known limitations" updated with what's still missing (for
  example "metrics aren't scraped yet", "one Fargate task, no autoscaling").

## Done means

All 6 PRs merged with CI green, the app served from AWS behind the load
balancer, RESUME_FACTS.md filled in, and a summary per item. Steps that need
you are marked above. I'll stop and ask at each one.
