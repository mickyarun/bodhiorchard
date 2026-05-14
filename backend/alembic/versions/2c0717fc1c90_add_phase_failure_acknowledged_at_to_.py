"""add phase_failure_acknowledged_at to bud_documents

Revision ID: 2c0717fc1c90
Revises: de27cc187d79
Create Date: 2026-05-13 15:57:15.753814

Sticky-dismissal timestamp for the BUD detail "last phase failure"
banner. Any AgentActivityLog ``skill_failed`` row or BUDAgentTask
``failed`` row newer than this timestamp shows on the BUD detail; older
ones are hidden so a banner the user has already acknowledged doesn't
re-pop after a refresh.

Note: ``alembic revision --autogenerate`` also surfaced ``xlm_*`` drift
left over from the dropped cross-repo-merge phase (see memory note
``project_phase5_dropped``). That cleanup belongs in its own
migration; this revision is scoped to the new column only.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2c0717fc1c90"
down_revision: str | None = "de27cc187d79"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bud_documents",
        sa.Column(
            "phase_failure_acknowledged_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("bud_documents", "phase_failure_acknowledged_at")
