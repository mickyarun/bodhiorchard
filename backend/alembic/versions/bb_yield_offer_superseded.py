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

"""Extend yield_offer_status enum with superseded.

A yield offer asks a developer to give up a lower-priority BUD so they
can take a higher-priority one that has no assignee. Once that incoming
BUD is assigned by any other route, the offer's premise no longer holds
and it must be closed out — but it did not time out, so reusing
`expired` would blur the audit trail between "nobody answered" and
"the question stopped mattering".

Autogenerate does not diff Postgres enum values, so this is written by
hand, following the same ADD VALUE pattern as
`zg_race_invite_notification` and `a1_add_tech_arch_and_manager`.

Revision ID: bb_yield_superseded
Revises: ba_backlash_game
Create Date: 2026-08-18
"""

from collections.abc import Sequence

from alembic import op

revision: str = "bb_yield_superseded"
down_revision: str | None = "ba_backlash_game"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the `superseded` value to `yield_offer_status`.

    PostgreSQL ADD VALUE is non-transactional, so it runs in its own
    `execute()` call. `IF NOT EXISTS` keeps the migration idempotent
    across re-runs and partially-migrated environments.
    """
    op.execute("ALTER TYPE yield_offer_status ADD VALUE IF NOT EXISTS 'superseded'")


def downgrade() -> None:
    """No-op.

    PostgreSQL cannot drop a value from an enum type. Removing it would
    mean recreating the type and rewriting every dependent column, which
    is far more destructive than leaving an unused label in place.
    """
