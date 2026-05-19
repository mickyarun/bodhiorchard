"""add bud_id to reward_events

Revision ID: e3153001b6ee
Revises: 56fa72b2cc1c
Create Date: 2026-05-19 19:30:08.542996

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e3153001b6ee"
down_revision: str | None = "56fa72b2cc1c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "reward_events",
        sa.Column("bud_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_reward_events_bud_id",
        "reward_events",
        "bud_documents",
        ["bud_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_reward_events_user_bud_source",
        "reward_events",
        ["org_id", "user_id", "bud_id", "source"],
        unique=False,
        postgresql_where="bud_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index(
        "ix_reward_events_user_bud_source",
        table_name="reward_events",
        postgresql_where="bud_id IS NOT NULL",
    )
    op.drop_constraint("fk_reward_events_bud_id", "reward_events", type_="foreignkey")
    op.drop_column("reward_events", "bud_id")
