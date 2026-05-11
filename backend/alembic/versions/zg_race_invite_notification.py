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

"""Extend notification_type enum with race_invite + add meta column.

Adds `race_invite` to the `notification_type` Postgres enum so the
race-v2 invite flow can write its own notification rows, and adds a
nullable `meta` JSONB column so race-specific fields (host name,
distance, room id) survive server restarts for the bell dropdown.

The new column is named `meta` (not `metadata`) to avoid conflicting
with SQLAlchemy's reserved `Base.metadata` attribute. It's deliberately
generic so future notification types can reuse it for their own
structured payloads rather than overloading `job_id` / `title`.

Revision ID: zg_race_invite
Revises: 039479826ecb
Create Date: 2026-04-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zg_race_invite"
down_revision: str | None = "039479826ecb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Extend enum + add metadata column.

    PostgreSQL ADD VALUE is non-transactional, so it must run outside a
    transaction block via its own ``execute()`` call (same pattern as
    ``a1_add_tech_arch_and_manager``).
    """
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'race_invite'")

    op.add_column(
        "notifications",
        sa.Column("meta", postgresql.JSONB, nullable=True),
    )


def downgrade() -> None:
    """Drop the meta column. Enum values cannot be removed in Postgres."""
    op.drop_column("notifications", "meta")
