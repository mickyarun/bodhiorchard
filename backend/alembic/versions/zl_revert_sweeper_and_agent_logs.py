"""Revert heartbeat sweeper; drop dead agent_logs table.

Two cleanups bundled:

1. The heartbeat + wall-clock sweeper on ``bud_agent_tasks`` was too
   aggressive — tasks that legitimately took > 3 min to reach their
   first heartbeat got swept to failed. We're removing the whole
   mechanism in favour of a manual "cancel job" button in the UI.
   Drops ``last_heartbeat_at`` and its partial index.

2. ``agent_logs`` was declared in an earlier design and never wired —
   zero writers in the codebase, zero rows in any installation.
   ``agent_activity_logs`` replaced it. Dropping the dead table.

Revision ID: zl_revert_sweeper
Revises: zk_agent_task_hb
Create Date: 2026-04-22
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zl_revert_sweeper"
down_revision: str | None = "zk_agent_task_hb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Remove the heartbeat column + partial index.
    op.drop_index(
        "ix_bud_agent_tasks_running_heartbeat",
        table_name="bud_agent_tasks",
    )
    op.drop_column("bud_agent_tasks", "last_heartbeat_at")

    # 2. Drop the unused agent_logs table.
    op.drop_table("agent_logs")


def downgrade() -> None:
    # Recreate agent_logs with its original schema (copied from the
    # initial-commit DDL). Kept downgradeable so the migration can be
    # rolled back in a pinch.
    op.create_table(
        "agent_logs",
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("agent_name", sa.String(length=255), nullable=False),
        sa.Column("trigger_type", sa.String(length=100), nullable=True),
        sa.Column("trigger_source", sa.String(length=255), nullable=True),
        sa.Column("input_summary", sa.Text(), nullable=True),
        sa.Column("output_summary", sa.Text(), nullable=True),
        sa.Column("tokens_used", sa.Integer(), nullable=True),
        sa.Column("execution_time_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    # Restore the heartbeat column + index.
    op.add_column(
        "bud_agent_tasks",
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_bud_agent_tasks_running_heartbeat",
        "bud_agent_tasks",
        ["last_heartbeat_at"],
        postgresql_where=sa.text("status = 'running'"),
    )
