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

"""Add agent_skill_overrides table for per-org prompt customization.

Revision ID: x4e5f6a7b8
Revises: w3f4g5h6i7
Create Date: 2026-03-21 16:00:00.000000
"""

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSONB, UUID

from alembic import op

revision = "x4e5f6a7b8"
down_revision = "w3f4g5h6i7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agent_skill_overrides",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("skill_slug", sa.String(100), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
        sa.Column("tools", JSONB, nullable=False, server_default="[]"),
        sa.Column("mcp_tools", JSONB, nullable=False, server_default="[]"),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "skill_slug", name="uq_skill_override_org_slug"),
    )
    op.create_index("ix_agent_skill_overrides_org_id", "agent_skill_overrides", ["org_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_skill_overrides_org_id")
    op.drop_table("agent_skill_overrides")
