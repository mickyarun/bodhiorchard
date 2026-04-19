"""Add max_turns column to agent_skill_overrides.

Revision ID: y5f6a7b8c9
Revises: x4e5f6a7b8
Create Date: 2026-03-22 12:00:00.000000
"""

import sqlalchemy as sa

from alembic import op

revision = "y5f6a7b8c9"
down_revision = "x4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "agent_skill_overrides",
        sa.Column("max_turns", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("agent_skill_overrides", "max_turns")
