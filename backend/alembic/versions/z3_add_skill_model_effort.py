"""Add model and effort columns to agent_skill_overrides.

Revision ID: z3_add_skill_model_effort
Revises: z2_add_design_path
Create Date: 2026-03-23 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "z3_add_skill_model_effort"
down_revision: str = "z2_add_design_path"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add model and effort columns to agent_skill_overrides."""
    op.add_column(
        "agent_skill_overrides",
        sa.Column("model", sa.String(100), nullable=False, server_default=""),
    )
    op.add_column(
        "agent_skill_overrides",
        sa.Column("effort", sa.String(20), nullable=False, server_default=""),
    )


def downgrade() -> None:
    """Remove model and effort columns from agent_skill_overrides."""
    op.drop_column("agent_skill_overrides", "effort")
    op.drop_column("agent_skill_overrides", "model")
