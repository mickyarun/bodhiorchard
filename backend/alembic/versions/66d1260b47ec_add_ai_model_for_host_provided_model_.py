"""add ai model for host-provided model lists

Revision ID: 66d1260b47ec
Revises: 15f7ba3c12a9
Create Date: 2026-07-16 11:43:35.122289

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "66d1260b47ec"
down_revision: str | None = "15f7ba3c12a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("organizations", sa.Column("ai_model", sa.String(length=120), nullable=True))


def downgrade() -> None:
    op.drop_column("organizations", "ai_model")
