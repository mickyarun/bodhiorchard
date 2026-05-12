"""add iteration_model to agent_skills

Revision ID: db71468736e3
Revises: 9ec875b34b71
Create Date: 2026-05-13 00:41:25.599959

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "db71468736e3"
down_revision: Union[str, None] = "9ec875b34b71"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add ``iteration_model`` column to ``agent_skills``.

    Note: autogen also flagged a stack of leftover ``xlm_*`` experiment
    tables that exist only on this developer's local DB (Phase 5
    cross-layer merge work — see memory: phase5_dropped). Those drops
    are intentionally *not* in this migration: prod has never had those
    tables, so emitting drops would break the prod upgrade. Local
    cleanup is a separate, manual step.
    """
    op.add_column(
        "agent_skills",
        sa.Column(
            "iteration_model",
            sa.String(length=100),
            server_default="",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Drop the ``iteration_model`` column."""
    op.drop_column("agent_skills", "iteration_model")

