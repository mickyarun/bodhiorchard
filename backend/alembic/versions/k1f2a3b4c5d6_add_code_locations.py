"""Add code_locations JSON column to knowledge_items.

Revision ID: k1f2a3b4c5d6
Revises: j0e1f2a3b4c5
Create Date: 2026-03-20 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "k1f2a3b4c5d6"
down_revision: str | None = "j0e1f2a3b4c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add code_locations column."""
    op.add_column("knowledge_items", sa.Column("code_locations", sa.JSON, nullable=True))


def downgrade() -> None:
    """Remove code_locations column."""
    op.drop_column("knowledge_items", "code_locations")
