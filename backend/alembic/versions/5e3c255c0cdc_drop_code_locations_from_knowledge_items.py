"""drop code_locations from knowledge_items

Revision ID: 5e3c255c0cdc
Revises: z9_add_restrict_to_skill_fk
Create Date: 2026-03-25 18:13:20.793126

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '5e3c255c0cdc'
down_revision: Union[str, None] = 'z9_add_restrict_to_skill_fk'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column('knowledge_items', 'code_locations')


def downgrade() -> None:
    op.add_column('knowledge_items', sa.Column('code_locations', sa.JSON(), nullable=True))
