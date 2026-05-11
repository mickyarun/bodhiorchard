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

"""Add triage_sessions table and slack_team_id to organizations.

Revision ID: o5d6e7f8a9b0
Revises: n4c5d6e7f8a9
Create Date: 2026-03-20 23:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "o5d6e7f8a9b0"
down_revision: str = "n4c5d6e7f8a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add slack_team_id column and triage_sessions table."""
    # Add slack_team_id to organizations
    op.add_column(
        "organizations",
        sa.Column("slack_team_id", sa.String(50), nullable=True),
    )
    op.create_index("ix_organizations_slack_team_id", "organizations", ["slack_team_id"])

    # Create triage_sessions table
    op.create_table(
        "triage_sessions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("slack_channel", sa.String(50), nullable=False),
        sa.Column("thread_ts", sa.String(50), nullable=False),
        sa.Column("original_msg_ts", sa.String(50), nullable=False),
        sa.Column("summary_msg_ts", sa.String(50), nullable=True),
        sa.Column("requester_slack_id", sa.String(50), nullable=False),
        sa.Column("requester_name", sa.String(255), nullable=True),
        sa.Column("original_text", sa.Text, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="interviewing"),
        sa.Column("priority", sa.String(20), nullable=True),
        sa.Column("feature_name", sa.String(500), nullable=True),
        sa.Column("triage_context", JSONB, nullable=True),
        sa.Column(
            "bud_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bud_documents.id"),
            nullable=True,
        ),
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
        sa.UniqueConstraint("org_id", "slack_channel", "thread_ts", name="uq_triage_org_thread"),
    )
    op.create_index("ix_triage_org_status", "triage_sessions", ["org_id", "status"])


def downgrade() -> None:
    """Remove triage_sessions table and slack_team_id column."""
    op.drop_index("ix_triage_org_status", table_name="triage_sessions")
    op.drop_table("triage_sessions")
    op.drop_index("ix_organizations_slack_team_id", table_name="organizations")
    op.drop_column("organizations", "slack_team_id")
