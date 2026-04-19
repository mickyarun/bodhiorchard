"""Add design_path column to bud_designs table.

Revision ID: z2_add_design_path
Revises: z1a2b3c4d5
Create Date: 2026-03-22 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "z2_add_design_path"
down_revision: str = "z1a2b3c4d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add design_path column to bud_designs."""
    op.add_column(
        "bud_designs",
        sa.Column("design_path", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    """Remove design_path column from bud_designs."""
    op.drop_column("bud_designs", "design_path")
