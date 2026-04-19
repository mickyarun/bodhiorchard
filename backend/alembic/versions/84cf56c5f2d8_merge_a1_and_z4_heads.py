"""merge_a1_and_z4_heads

Revision ID: 84cf56c5f2d8
Revises: a1_add_tech_arch_and_manager, z4_add_code_review_and_commits
Create Date: 2026-03-23 19:38:34.820667

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '84cf56c5f2d8'
down_revision: Union[str, None] = ('a1_add_tech_arch_and_manager', 'z4_add_code_review_and_commits')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
