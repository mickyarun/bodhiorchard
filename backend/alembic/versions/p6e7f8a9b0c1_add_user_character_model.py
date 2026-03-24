"""Add character_model column to users table.

Revision ID: p6e7f8a9b0c1
Revises: o5d6e7f8a9b0
Create Date: 2026-03-20 23:30:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "p6e7f8a9b0c1"
down_revision: str | None = "o5d6e7f8a9b0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add character_model to users for garden dashboard character preference."""
    op.add_column("users", sa.Column("character_model", sa.String(100), nullable=True))


def downgrade() -> None:
    """Remove character_model from users."""
    op.drop_column("users", "character_model")
