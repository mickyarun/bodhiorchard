"""merge zd_bug_type and ze_sp_numeric

Revision ID: b8ac63b0ee7a
Revises: zd_bug_type_column, ze_sp_numeric
Create Date: 2026-04-12 23:40:54.134987

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b8ac63b0ee7a'
down_revision: Union[str, None] = ('zd_bug_type_column', 'ze_sp_numeric')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
