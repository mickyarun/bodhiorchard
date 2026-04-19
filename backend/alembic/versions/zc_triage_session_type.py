"""Add session_type to triage_sessions for bug vs BUD triage.

Revision ID: zc_triage_session_type
Revises: zb_bud_release_tracking
Create Date: 2026-04-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zc_triage_session_type"
down_revision: str | None = "zb_bud_release_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add session_type column with default 'bud'."""
    op.add_column(
        "triage_sessions",
        sa.Column(
            "session_type",
            sa.String(length=10),
            nullable=False,
            server_default="bud",
        ),
    )


def downgrade() -> None:
    """Drop session_type column."""
    op.drop_column("triage_sessions", "session_type")
