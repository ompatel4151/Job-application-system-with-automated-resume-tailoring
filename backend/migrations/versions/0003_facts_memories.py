"""facts and memories: the agent's per-user data, under the same RLS as 0002

Also adds tailored_resumes.agent_trace (null for plain mode).

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-02
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

NEW = ("resume_facts", "agent_memories")


def upgrade() -> None:
    op.create_table(
        "resume_facts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("fact_id", sa.String(length=40), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("numbers", sa.JSON(), nullable=False),
        sa.Column("tools", sa.JSON(), nullable=False),
        sa.Column("context", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "fact_id", name="uq_resume_facts_user_fact"),
    )
    op.create_table(
        "agent_memories",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("text", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_agent_memories_user_created", "agent_memories", ["user_id", "created_at", "id"])
    with op.batch_alter_table("tailored_resumes") as batch:
        batch.add_column(sa.Column("agent_trace", sa.JSON(), nullable=True))

    if op.get_bind().dialect.name != "postgresql":
        return
    # 0002 already made the authenticated role and auth.uid().
    for table in NEW:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"REVOKE ALL ON {table} FROM authenticated")
        op.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO authenticated")
        op.execute(
            f"CREATE POLICY own_rows ON {table} FOR ALL TO authenticated "
            "USING (user_id = auth.uid()) WITH CHECK (user_id = auth.uid())"
        )
        op.execute(
            f"DO $$ BEGIN IF EXISTS (SELECT FROM pg_roles WHERE rolname = 'anon') "
            f"THEN REVOKE ALL ON {table} FROM anon; END IF; END $$"
        )
    op.execute("GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO authenticated")


def downgrade() -> None:
    with op.batch_alter_table("tailored_resumes") as batch:
        batch.drop_column("agent_trace")
    op.drop_index("ix_agent_memories_user_created", table_name="agent_memories")
    op.drop_table("agent_memories")
    op.drop_table("resume_facts")
