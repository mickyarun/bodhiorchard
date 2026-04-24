"""Move code_locations to knowledge_to_repo junction table.

Adds a code_locations JSON column to the junction table so each
repo-feature link tracks its own code paths. Migrates existing data
from knowledge_items.code_locations to the junction rows.

Revision ID: m5_code_locations_to_junction
Revises: 402d2f21dcfa
Create Date: 2026-03-25

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "m5_code_locations_to_junction"
down_revision: str | None = "402d2f21dcfa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Move code_locations from knowledge_items to knowledge_to_repo."""
    # 1. Add column to junction table
    op.add_column(
        "knowledge_to_repo",
        sa.Column("code_locations", sa.JSON(), nullable=True),
    )

    # 2. Copy data from knowledge_items to each linked junction row
    op.execute("""
        UPDATE knowledge_to_repo ktr
        SET code_locations = ki.code_locations
        FROM knowledge_items ki
        WHERE ktr.knowledge_id = ki.id
          AND ki.code_locations IS NOT NULL
          AND ki.code_locations::jsonb != '{}'::jsonb
    """)


def downgrade() -> None:
    """Remove code_locations from knowledge_to_repo."""
    op.drop_column("knowledge_to_repo", "code_locations")
