"""add org-scoped bug_number sequence

Revision ID: c1d2e3f4a5b6
Revises: b656380431cb
Create Date: 2026-06-18 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1d2e3f4a5b6"
down_revision: str | None = "b656380431cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Bugs gain a human-readable, org-scoped sequence (rendered BUG-001),
    # mirroring ``bud_documents.bud_number``. Three steps so the NOT NULL +
    # unique constraint can be added safely on top of existing rows:
    #   1. add the column nullable,
    #   2. backfill a per-org sequence ordered by created_at (oldest = 1),
    #   3. enforce NOT NULL + uniqueness.
    op.add_column("bugs", sa.Column("bug_number", sa.Integer(), nullable=True))

    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY org_id
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM bugs
            )
            UPDATE bugs
            SET bug_number = ranked.rn
            FROM ranked
            WHERE bugs.id = ranked.id;
            """
        )
    )

    op.alter_column("bugs", "bug_number", existing_type=sa.Integer(), nullable=False)
    op.create_unique_constraint("uq_bug_org_number", "bugs", ["org_id", "bug_number"])


def downgrade() -> None:
    op.drop_constraint("uq_bug_org_number", "bugs", type_="unique")
    op.drop_column("bugs", "bug_number")
