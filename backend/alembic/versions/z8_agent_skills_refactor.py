"""Rename agent_skill_overrides to agent_skills, add stage mapping and task tables.

Part A: Rename agent_skill_overrides → agent_skills (DB-first, not override)
Part B: Create agent_skill_bud_stages (maps which skill runs at which BUD stage)
Part C: Create bud_agent_tasks (persistent agent task tracking with retry)

Revision ID: z8_agent_skills_refactor
Revises: m5_code_locations_to_junction
Create Date: 2026-03-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision: str = "z8_agent_skills_refactor"
down_revision: str | None = "m5_code_locations_to_junction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename agent_skill_overrides, create stage mapping and task tables."""
    # ── Part A: Rename agent_skill_overrides → agent_skills ──
    op.rename_table("agent_skill_overrides", "agent_skills")
    op.execute("ALTER INDEX ix_agent_skill_overrides_org_id RENAME TO ix_agent_skills_org_id")
    op.execute(
        "ALTER TABLE agent_skills "
        "RENAME CONSTRAINT uq_skill_override_org_slug TO uq_skill_org_slug"
    )

    # ── Part B: Create agent_skill_bud_stages ──
    op.create_table(
        "agent_skill_bud_stages",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "skill_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_skills.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("bud_status", sa.String(30), nullable=False),
        sa.Column("execution_order", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("output_section", sa.String(50), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "org_id",
            "bud_status",
            "execution_order",
            name="uq_skill_bud_stage_org_status_order",
        ),
    )
    op.create_index(
        "ix_agent_skill_bud_stages_org_id",
        "agent_skill_bud_stages",
        ["org_id"],
    )

    # ── Part C: Create bud_agent_tasks ──
    op.create_table(
        "bud_agent_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "bud_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bud_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "skill_id",
            UUID(as_uuid=True),
            sa.ForeignKey("agent_skills.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("task_type", sa.String(30), nullable=False),
        sa.Column(
            "status",
            sa.String(20),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("job_id", sa.String(100), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("status_message", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("result_summary", JSONB, nullable=True),
        sa.Column(
            "triggered_by",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_bud_agent_tasks_bud_status",
        "bud_agent_tasks",
        ["bud_id", "status"],
    )
    op.create_index(
        "ix_bud_agent_tasks_org_status",
        "bud_agent_tasks",
        ["org_id", "status"],
    )
    op.create_index(
        "ix_bud_agent_tasks_job_id",
        "bud_agent_tasks",
        ["job_id"],
    )
    # At most one pending/running task per BUD at any time
    op.execute(
        "CREATE UNIQUE INDEX uq_bud_agent_tasks_one_active "
        "ON bud_agent_tasks (bud_id) WHERE status IN ('pending', 'running')"
    )


def downgrade() -> None:
    """Reverse: drop new tables, rename agent_skills back."""
    # Drop bud_agent_tasks
    op.execute("DROP INDEX IF EXISTS uq_bud_agent_tasks_one_active")
    op.drop_index("ix_bud_agent_tasks_job_id")
    op.drop_index("ix_bud_agent_tasks_org_status")
    op.drop_index("ix_bud_agent_tasks_bud_status")
    op.drop_table("bud_agent_tasks")

    # Drop agent_skill_bud_stages
    op.drop_index("ix_agent_skill_bud_stages_org_id")
    op.drop_table("agent_skill_bud_stages")

    # Rename agent_skills back to agent_skill_overrides
    op.execute(
        "ALTER TABLE agent_skills "
        "RENAME CONSTRAINT uq_skill_org_slug TO uq_skill_override_org_slug"
    )
    op.execute("ALTER INDEX ix_agent_skills_org_id RENAME TO ix_agent_skill_overrides_org_id")
    op.rename_table("agent_skills", "agent_skill_overrides")
