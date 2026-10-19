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
