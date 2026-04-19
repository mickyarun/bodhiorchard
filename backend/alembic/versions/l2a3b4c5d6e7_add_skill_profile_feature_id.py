"""Add feature_id FK to skill_profiles.

Revision ID: l2a3b4c5d6e7
Revises: k1f2a3b4c5d6
Create Date: 2026-03-20 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "l2a3b4c5d6e7"
down_revision: str | None = "k1f2a3b4c5d6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add feature_id column with FK and index."""
    op.add_column(
        "skill_profiles",
        sa.Column(
            "feature_id",
            sa.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_sp_feature_id", "skill_profiles", ["feature_id"])


def downgrade() -> None:
    """Remove feature_id column."""
    op.drop_index("ix_sp_feature_id", table_name="skill_profiles")
    op.drop_column("skill_profiles", "feature_id")
