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

"""Add BUD assignee_id column and bud_timeline_events table.

Revision ID: z1a2b3c4d5
Revises: y5f6a7b8c9
Create Date: 2026-03-22 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "z1a2b3c4d5"
down_revision: str = "y5f6a7b8c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add assignee_id to bud_documents and create bud_timeline_events table."""
    # Add assignee_id column to bud_documents
    op.add_column(
        "bud_documents",
        sa.Column(
            "assignee_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )

    # Create bud_timeline_events table
    op.create_table(
        "bud_timeline_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "bud_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bud_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column(
            "actor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("actor_name", sa.String(255), nullable=True),
        sa.Column("detail", JSONB, nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_bud_timeline_bud_id", "bud_timeline_events", ["bud_id"])


def downgrade() -> None:
    """Remove bud_timeline_events table and assignee_id column."""
    op.drop_index("ix_bud_timeline_bud_id", table_name="bud_timeline_events")
    op.drop_table("bud_timeline_events")
    op.drop_column("bud_documents", "assignee_id")
