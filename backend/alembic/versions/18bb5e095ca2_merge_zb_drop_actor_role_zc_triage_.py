"""merge zb_drop_actor_role + zc_triage_session_type

Revision ID: 18bb5e095ca2
Revises: zb_drop_actor_role_column, zc_triage_session_type
Create Date: 2026-04-12 19:49:28.443489

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '18bb5e095ca2'
down_revision: Union[str, None] = ('zb_drop_actor_role_column', 'zc_triage_session_type')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
