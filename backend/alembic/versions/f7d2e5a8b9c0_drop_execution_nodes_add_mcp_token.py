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

"""Drop execution_nodes table and add mcp_token_hash to organizations.

Revision ID: f7d2e5a8b9c0
Revises: e6c1d4f5a7b8
Create Date: 2026-03-17 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f7d2e5a8b9c0"
down_revision: str | None = "e6c1d4f5a7b8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop execution_nodes and add mcp_token_hash to organizations."""
    op.add_column("organizations", sa.Column("mcp_token_hash", sa.Text(), nullable=True))
    op.drop_index("ix_execution_nodes_org_id", table_name="execution_nodes")
    op.drop_table("execution_nodes")


def downgrade() -> None:
    """Recreate execution_nodes and remove mcp_token_hash from organizations."""
    op.create_table(
        "execution_nodes",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        sa.Column("lan_ip", sa.String(length=45), nullable=True),
        sa.Column("tailscale_ip", sa.String(length=45), nullable=True),
        sa.Column("advertised_url", sa.String(length=500), nullable=True),
        sa.Column("health_port", sa.Integer(), nullable=False),
        sa.Column("execution_mode", sa.String(length=50), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("discovery_method", sa.String(length=50), nullable=True),
        sa.Column("capabilities", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("cli_version", sa.String(length=50), nullable=True),
        sa.Column("os_info", sa.String(length=255), nullable=True),
        sa.Column("max_concurrent", sa.Integer(), nullable=False),
        sa.Column("repos", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("node_token_hash", sa.Text(), nullable=True),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=True),
        sa.Column("active_task_count", sa.Integer(), nullable=False),
        sa.Column("cpu_percent", sa.Float(), nullable=True),
        sa.Column("ram_percent", sa.Float(), nullable=True),
        sa.Column("total_tasks_completed", sa.Integer(), nullable=False),
        sa.Column("total_tasks_failed", sa.Integer(), nullable=False),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["approved_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_execution_nodes_org_id", "execution_nodes", ["org_id"], unique=False)
    op.drop_column("organizations", "mcp_token_hash")
