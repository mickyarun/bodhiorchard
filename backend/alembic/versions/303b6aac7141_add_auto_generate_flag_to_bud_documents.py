"""add auto_generate flag to bud_documents

Revision ID: 303b6aac7141
Revises: 15f415a484f1
Create Date: 2026-05-19 12:10:09.364552

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "303b6aac7141"
down_revision: str | None = "15f415a484f1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "bud_documents",
        sa.Column(
            "auto_generate",
            sa.Boolean(),
            server_default=sa.text("true"),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("bud_documents", "auto_generate")
