"""design_system_refs add custom_content

Revision ID: 56fa72b2cc1c
Revises: 15f415a484f1
Create Date: 2026-05-19 13:48:24.202143

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '56fa72b2cc1c'
down_revision: Union[str, None] = '15f415a484f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'design_system_refs',
        sa.Column('custom_content', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('design_system_refs', 'custom_content')
