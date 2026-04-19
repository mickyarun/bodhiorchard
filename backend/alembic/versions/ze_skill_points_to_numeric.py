"""skill_points Integer to Numeric(10,2) for fractional SP economy

Revision ID: ze_sp_numeric
Revises: 3922c4bb35ad
Create Date: 2026-04-13

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "ze_sp_numeric"
down_revision: Union[str, None] = "3922c4bb35ad"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Convert skill_points from Integer to Numeric(10,2) for fractional SP.
    # Reset all values to 0 — old 1:1 SP economy is replaced by role-based awards.
    op.alter_column(
        "developer_xp",
        "skill_points",
        type_=sa.Numeric(10, 2),
        existing_type=sa.Integer(),
        existing_nullable=False,
        existing_server_default="0",
        server_default="0",
    )
    op.execute("UPDATE developer_xp SET skill_points = 0")


def downgrade() -> None:
    op.alter_column(
        "developer_xp",
        "skill_points",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2),
        existing_nullable=False,
        existing_server_default="0",
        server_default="0",
        postgresql_using="skill_points::integer",
    )
