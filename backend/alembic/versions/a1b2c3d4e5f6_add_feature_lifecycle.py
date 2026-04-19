"""Add feature lifecycle: feature_status column and cancelled PRD status.

Revision ID: a1b2c3d4e5f6
Revises: f7d2e5a8b9c0
Create Date: 2026-03-19 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | None = "f7d2e5a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add feature_status to knowledge_items and cancelled to prd_status enum."""
    op.add_column("knowledge_items", sa.Column("feature_status", sa.String(20), nullable=True))
    op.create_index("ix_knowledge_items_feature_status", "knowledge_items", ["feature_status"])
    op.execute("ALTER TYPE prd_status ADD VALUE IF NOT EXISTS 'cancelled'")


def downgrade() -> None:
    """Remove feature_status column. Cannot remove enum value in PostgreSQL."""
    op.drop_index("ix_knowledge_items_feature_status", table_name="knowledge_items")
    op.drop_column("knowledge_items", "feature_status")
    # PostgreSQL does not support removing values from an enum type.
    # The 'cancelled' value in prd_status will remain but is harmless.
