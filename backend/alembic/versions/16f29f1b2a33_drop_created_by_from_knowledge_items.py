"""drop created_by from knowledge_items

Revision ID: 16f29f1b2a33
Revises: 5e3c255c0cdc
Create Date: 2026-03-25 20:24:54.188503

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "16f29f1b2a33"
down_revision: str | None = "5e3c255c0cdc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("knowledge_items", "created_by")


def downgrade() -> None:
    op.add_column(
        "knowledge_items",
        sa.Column("created_by", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(None, "knowledge_items", "users", ["created_by"], ["id"])
