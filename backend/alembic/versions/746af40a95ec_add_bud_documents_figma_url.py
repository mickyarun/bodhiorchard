"""add_bud_documents_figma_url

Revision ID: 746af40a95ec
Revises: 6e375ee9d275
Create Date: 2026-05-21 23:11:54.414645

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '746af40a95ec'
down_revision: Union[str, None] = '6e375ee9d275'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'bud_documents',
        sa.Column('figma_url', sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('bud_documents', 'figma_url')
