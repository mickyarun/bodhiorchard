"""add active_job pointer to bud_section_sessions

Adds three nullable columns to ``bud_section_sessions`` —
``active_job_id``, ``active_job_status``, ``active_job_started_at`` —
plus a partial index ``ix_bud_section_sessions_active_job`` keyed on
``(bud_id, section, design_id) WHERE active_job_id IS NOT NULL`` for the
boot-time orphan sweep added later in this branch. The
``chat_active_job_status`` enum is created via raw SQL (same pattern as
``zn_scan_phase_checkpoints``) so the column reference uses
``create_type=False``.

Inspected after ``alembic revision --autogenerate``. Stripped from the
autogen output, as they are unrelated to this change set and reflect
local-DB drift only: nine ``drop_table('xlm_*')`` calls left over from
the dropped phase-5 GitNexus cross-repo merge POC, and one
``drop_column('roles', 'base_role')`` covered by a prior migration.

Revision ID: 88f86e7e5e03
Revises: 7ae55c9d056a
Create Date: 2026-05-15 12:57:11.927167

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "88f86e7e5e03"
down_revision: str | None = "7ae55c9d056a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("CREATE TYPE chat_active_job_status AS ENUM ('queued', 'running')")
    op.add_column(
        "bud_section_sessions",
        sa.Column("active_job_id", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "bud_section_sessions",
        sa.Column(
            "active_job_status",
            postgresql.ENUM("queued", "running", name="chat_active_job_status", create_type=False),
            nullable=True,
        ),
    )
    op.add_column(
        "bud_section_sessions",
        sa.Column("active_job_started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_bud_section_sessions_active_job",
        "bud_section_sessions",
        ["bud_id", "section", "design_id"],
        unique=False,
        postgresql_where="active_job_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_bud_section_sessions_active_job",
        table_name="bud_section_sessions",
    )
    op.drop_column("bud_section_sessions", "active_job_started_at")
    op.drop_column("bud_section_sessions", "active_job_status")
    op.drop_column("bud_section_sessions", "active_job_id")
    op.execute("DROP TYPE IF EXISTS chat_active_job_status")
