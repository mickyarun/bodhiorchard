"""add must_change_password to users

Revision ID: 402d2f21dcfa
Revises: m4_embedding_384
Create Date: 2026-03-25 12:06:57.822738

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '402d2f21dcfa'
down_revision: Union[str, None] = 'm4_embedding_384'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'users',
        sa.Column('must_change_password', sa.Boolean(), server_default='false', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('users', 'must_change_password')
