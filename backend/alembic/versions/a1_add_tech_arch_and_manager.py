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

"""Add tech_arch status, manager role, and lifecycle notification types.

Revision ID: a1_add_tech_arch_and_manager
Revises: z3_add_skill_model_effort
Create Date: 2026-03-23 14:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1_add_tech_arch_and_manager"
down_revision: str = "z3_add_skill_model_effort"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add new enum values for tech_arch phase, manager role, and notifications.

    PostgreSQL ADD VALUE is non-transactional, so each runs in its own
    execute() call outside a transaction block.
    """
    # BUDStatus (DB enum name: bud_status)
    op.execute("ALTER TYPE bud_status ADD VALUE IF NOT EXISTS 'tech_arch'")

    # UserRole (DB enum name: user_role)
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'manager'")

    # BUDTimelineEventType — NOT a DB enum. The event_type column is
    # String(30), so new values need no migration. The Python StrEnum is
    # used only for code-level validation.

    # NotificationType (DB enum name: notification_type)
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'approval_requested'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'approval_granted'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'approval_rejected'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'developer_assigned'")
    op.execute("ALTER TYPE notification_type ADD VALUE IF NOT EXISTS 'reassignment_done'")


def downgrade() -> None:
    """PostgreSQL does not support removing enum values."""
