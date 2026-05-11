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

"""Create race_results table for the persistent race leaderboard.

Adds the source-of-truth table for completed races: one row per
participant per race, written by the multiplayer server when a
RaceRoom disposes. Idempotent on (room_id, user_id) so bridge retries
don't double-count.

Two composite indexes cover the hot queries:
  - (org_id, distance_m, finish_time_ms)   →  leaderboard ORDER BY time
  - (org_id, user_id, distance_m)          →  "my personal best"

A CHECK constraint mirrors ALLOWED_DISTANCES_M = {100, 200} from the
shared race constants so the DB refuses rows the application forgot
to validate.

Revision ID: zh_race_results
Revises: zg_race_invite
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zh_race_results"
down_revision: str | None = "zg_race_invite"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "race_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("room_id", sa.String(), nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "host_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("distance_m", sa.Integer(), nullable=False),
        sa.Column("finish_time_ms", sa.Integer(), nullable=True),
        sa.Column("place", sa.Integer(), nullable=False),
        sa.Column("finished", sa.Boolean(), nullable=False),
        sa.Column("distance_m_reached", sa.Float(), nullable=False),
        sa.Column(
            "finished_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("room_id", "user_id", name="uq_race_results_room_user"),
        sa.CheckConstraint(
            "distance_m IN (100, 200)",
            name="ck_race_results_distance_m",
        ),
    )
    op.create_index(
        "ix_race_results_org_distance_time",
        "race_results",
        ["org_id", "distance_m", "finish_time_ms"],
    )
    op.create_index(
        "ix_race_results_org_user_distance",
        "race_results",
        ["org_id", "user_id", "distance_m"],
    )


def downgrade() -> None:
    op.drop_table("race_results")
