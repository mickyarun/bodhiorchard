"""drop code_locations from knowledge_items

Revision ID: 5e3c255c0cdc
Revises: z9_add_restrict_to_skill_fk
Create Date: 2026-03-25 18:13:20.793126

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5e3c255c0cdc"
down_revision: str | None = "z9_add_restrict_to_skill_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("knowledge_items", "code_locations")


def downgrade() -> None:
    op.add_column("knowledge_items", sa.Column("code_locations", sa.JSON(), nullable=True))
