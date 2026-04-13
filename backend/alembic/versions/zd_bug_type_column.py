"""Add bug_type column to bugs table.

Classifies bugs as 'testing' (found during QA) or 'production' (found
after release). Auto-set based on BUD status at bug creation time.

Revision ID: zd_bug_type_column
Revises: zc_triage_session_type
Create Date: 2026-04-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zd_bug_type_column"
down_revision: str | None = "3922c4bb35ad"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add bug_type enum + column with default 'testing'."""
    bug_type_enum = sa.Enum("testing", "production", name="bug_type")
    bug_type_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "bugs",
        sa.Column(
            "bug_type",
            bug_type_enum,
            nullable=False,
            server_default="testing",
        ),
    )


def downgrade() -> None:
    """Drop bug_type column and enum."""
    op.drop_column("bugs", "bug_type")
    sa.Enum(name="bug_type").drop(op.get_bind(), checkfirst=True)
