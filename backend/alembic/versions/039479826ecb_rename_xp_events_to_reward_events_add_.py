# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""rename xp_events to reward_events, add type column

Revision ID: 039479826ecb
Revises: d9c7f018e768
Create Date: 2026-04-18 23:48:23.897093

In-place rename that preserves existing data. Converts xp_amount (Integer)
to amount (Numeric(10,2)), renames the table and its indexes, and adds a
reward_type enum column. SP-only rows (identified by metadata_->>'sp_amount')
are classified as type='sp' with amount set from that metadata; all other
rows are type='xp'. The existing sp_amount metadata is kept untouched so a
downgrade can round-trip without further work.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "039479826ecb"
down_revision: str | None = "d9c7f018e768"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Rename table
    op.rename_table("xp_events", "reward_events")

    # 2. Rename indexes so they match the new table name
    op.execute("ALTER INDEX ix_xp_events_user_org_time RENAME TO ix_reward_events_user_org_time")
    op.execute("ALTER INDEX ix_xp_events_org_time RENAME TO ix_reward_events_org_time")
    op.execute("ALTER INDEX uq_xp_events_source_ref RENAME TO uq_reward_events_source_ref")

    # 3. Rename xp_amount -> amount and promote to Numeric(10,2)
    op.alter_column(
        "reward_events",
        "xp_amount",
        new_column_name="amount",
        type_=sa.Numeric(10, 2, asdecimal=False),
        existing_type=sa.Integer(),
        postgresql_using="xp_amount::numeric(10,2)",
        nullable=False,
    )

    # 4. Create the reward_type enum
    reward_type = sa.Enum("xp", "sp", name="reward_type")
    reward_type.create(op.get_bind(), checkfirst=True)

    # 5. Add type column as nullable, backfill, then enforce NOT NULL
    op.add_column(
        "reward_events",
        sa.Column("type", reward_type, nullable=True),
    )

    # Rows the SP service wrote carry sp_amount in metadata — classify them as sp
    # and populate amount from that metadata (the historical xp_amount was 0).
    op.execute("""
        UPDATE reward_events
        SET type = 'sp',
            amount = (metadata_->>'sp_amount')::numeric(10,2)
        WHERE metadata_ ? 'sp_amount'
    """)

    # Everything else is XP.
    op.execute("UPDATE reward_events SET type = 'xp' WHERE type IS NULL")

    # Reclassify legacy greeting_bonus rows that the buggy endpoint wrote
    # directly (bypassing sp_service, so no sp_amount metadata marker): they
    # are semantically SP awards of 0.25, not XP. Without this fixup they
    # would permanently pollute `_collect_xp_earned` in standup reports.
    op.execute("""
        UPDATE reward_events
        SET type = 'sp', amount = 0.25
        WHERE source = 'greeting_bonus' AND type = 'xp' AND amount = 0
    """)

    op.alter_column("reward_events", "type", nullable=False)

    # 6. New composite index for type-filtered history queries
    op.create_index(
        "ix_reward_events_type_time",
        "reward_events",
        ["org_id", "type", "created_at"],
    )


def downgrade() -> None:
    # Reverse order: drop new index, drop type column, drop enum, revert column,
    # rename indexes back, rename table back.
    op.drop_index("ix_reward_events_type_time", table_name="reward_events")
    op.drop_column("reward_events", "type")

    sa.Enum(name="reward_type").drop(op.get_bind(), checkfirst=True)

    # Cast back to Integer — this is LOSSY for fractional SP values in the
    # audit table (e.g. 0.25 → 0). The DeveloperXP.skill_points aggregate is
    # unaffected because it's a separate column. The original sp_amount
    # metadata written by sp_service is still intact on those rows, so the
    # fractional values can be recovered from there if needed.
    op.alter_column(
        "reward_events",
        "amount",
        new_column_name="xp_amount",
        type_=sa.Integer(),
        existing_type=sa.Numeric(10, 2, asdecimal=False),
        postgresql_using="amount::integer",
        nullable=False,
    )

    op.execute("ALTER INDEX ix_reward_events_user_org_time RENAME TO ix_xp_events_user_org_time")
    op.execute("ALTER INDEX ix_reward_events_org_time RENAME TO ix_xp_events_org_time")
    op.execute("ALTER INDEX uq_reward_events_source_ref RENAME TO uq_xp_events_source_ref")

    op.rename_table("reward_events", "xp_events")
