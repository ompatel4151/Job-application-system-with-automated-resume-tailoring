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
