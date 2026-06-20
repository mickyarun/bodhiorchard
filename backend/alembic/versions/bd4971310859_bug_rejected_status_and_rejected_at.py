"""bug rejected status and rejected_at

Revision ID: bd4971310859
Revises: b656380431cb
Create Date: 2026-06-17 14:38:37.530615

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "bd4971310859"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Autogenerate does not diff Postgres enum *values*, so the new
    # ``rejected`` member of ``bug_status`` is added by hand. IF NOT EXISTS
    # keeps the migration idempotent; PG16 permits ADD VALUE inside the
    # migration transaction as long as the value isn't used in it.
    op.execute("ALTER TYPE bug_status ADD VALUE IF NOT EXISTS 'rejected'")
    op.add_column("bugs", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    # Postgres has no ``ALTER TYPE ... DROP VALUE``; the ``rejected`` enum
    # member is intentionally left in place on downgrade. Only the column
    # is reverted.
    op.drop_column("bugs", "rejected_at")
