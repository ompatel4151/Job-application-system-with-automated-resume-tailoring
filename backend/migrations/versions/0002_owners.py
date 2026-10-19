"""owners: every row belongs to a user, enforced by row-level security

Rows from before accounts have no owner. The live database had 0 rows when
this was written, so the migration refuses to run on a database that has any,
rather than guessing an owner or deleting data.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-18
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

OWNED = ("applications", "resumes", "tailored_resumes", "idempotency_keys")

# Supabase already has these; a plain Postgres (CI, docker-compose) doesn't.
# auth.uid() is Supabase's own definition, so policies behave the same on both.
SUPABASE_SHIM = """
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'authenticated') THEN
        CREATE ROLE authenticated NOLOGIN;
    END IF;
    IF NOT pg_has_role(current_user, 'authenticated', 'MEMBER') THEN
        EXECUTE format('GRANT authenticated TO %I', current_user);
    END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS auth;
DO $$
BEGIN
    IF to_regprocedure('auth.uid()') IS NULL THEN
        CREATE FUNCTION auth.uid() RETURNS uuid LANGUAGE sql STABLE AS $f$
            SELECT coalesce(
                nullif(current_setting('request.jwt.claim.sub', true), ''),
                (nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'sub')
            )::uuid
        $f$;
    END IF;
    -- On Supabase the auth schema belongs to supabase_admin and this grant
    -- already exists; only grant where we created the schema ourselves.
    IF NOT has_schema_privilege('authenticated', 'auth', 'USAGE') THEN
        GRANT USAGE ON SCHEMA auth TO authenticated;
    END IF;
    IF NOT has_schema_privilege('authenticated', 'public', 'USAGE') THEN
        GRANT USAGE ON SCHEMA public TO authenticated;
    END IF;
END $$;
"""


def upgrade() -> None:
    bind = op.get_bind()
    for table in OWNED:
        rows = bind.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar()
        if rows and table != "idempotency_keys":
            raise RuntimeError(
                f"{table} has {rows} rows with no owner. Assign them a user_id or "
                "delete them, then run the migration again."
            )

    # Idempotency rows are only a cache of recent responses; rebuild the table
    # with the new primary key rather than altering it.
    op.drop_table("idempotency_keys")
    op.create_table(
        "idempotency_keys",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("user_id", "key"),
    )
    for table in ("applications", "resumes", "tailored_resumes"):
        with op.batch_alter_table(table) as batch:
            batch.add_column(sa.Column("user_id", sa.Uuid(), nullable=False))
    op.create_index("ix_applications_user_updated", "applications", ["user_id", "updated_at", "id"])
    op.create_index("ix_resumes_user_created", "resumes", ["user_id", "created_at", "id"])

    if bind.dialect.name != "postgresql":
        return
    op.execute(SUPABASE_SHIM)
    for table in OWNED:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        # Only signed-in users, only their own rows, only plain DML. The
        # backend switches to this role per request (app.database).
        op.execute(f"REVOKE ALL ON {table} FROM authenticated")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO authenticated")
        op.execute(
            f"CREATE POLICY own_rows ON {table} FOR ALL TO authenticated "
            "USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())"
        )
        # Supabase's anonymous role gets nothing at all.
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') "
            f"THEN REVOKE ALL ON {table} FROM anon; END IF; END $$"
        )
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO authenticated")


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        for table in OWNED:
            op.execute(f"DROP POLICY IF EXISTS own_rows ON {table}")
    op.drop_index("ix_resumes_user_created", table_name="resumes")
    op.drop_index("ix_applications_user_updated", table_name="applications")
    for table in ("tailored_resumes", "resumes", "applications"):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("user_id")
    op.drop_table("idempotency_keys")
    op.create_table(
        "idempotency_keys",
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE idempotency_keys ENABLE ROW LEVEL SECURITY")
