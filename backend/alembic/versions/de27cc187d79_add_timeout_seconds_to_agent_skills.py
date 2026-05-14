"""add timeout_seconds to agent_skills

Revision ID: de27cc187d79
Revises: db71468736e3
Create Date: 2026-05-13 14:16:29.230640

Per-skill wall-clock cap on the Claude subprocess call, exposed in
Settings → Agent Prompts. ``0`` means "use the agent code's hard-coded
fallback" so existing rows keep current behaviour without backfill.

Note: ``alembic revision --autogenerate`` also surfaced ``xlm_*`` table
drift (left over from the dropped cross-repo-merge phase — see memory
note ``project_phase5_dropped``). That cleanup belongs in its own
migration; this revision is scoped to the new column only.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "de27cc187d79"
down_revision: str | None = "db71468736e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agent_skills",
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("agent_skills", "timeout_seconds")
