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

"""Add jira_import_sessions and jira_issue_bud_map tables.

Supports the Jira import pipeline: session tracking with progress
checkpoints for crash recovery, and per-issue traceability mapping
to BUD/Bug records with dedup constraints.

Revision ID: zf_jira_import
Revises: b8ac63b0ee7a
Create Date: 2026-04-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zf_jira_import"
down_revision: str | None = "b8ac63b0ee7a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "jira_import_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column("jira_project_key", sa.String(20), nullable=False),
        sa.Column("jira_project_name", sa.String(255), nullable=False),
        sa.Column("jira_site_id", sa.String(255), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("config", postgresql.JSONB, nullable=True),
        sa.Column("discovery_result", postgresql.JSONB, nullable=True),
        sa.Column("result", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("job_id", sa.String(100), nullable=True),
        sa.Column("total_issues", sa.Integer, nullable=True),
        sa.Column("processed_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_processed_key", sa.String(50), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
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
    )
    op.create_index(
        "ix_jira_import_org_status",
        "jira_import_sessions",
        ["org_id", "status"],
    )
    op.create_index(
        "ix_jira_import_org_project",
        "jira_import_sessions",
        ["org_id", "jira_project_key"],
    )

    op.create_table(
        "jira_issue_bud_map",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "import_session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("jira_import_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("jira_issue_key", sa.String(50), nullable=False),
        sa.Column("jira_issue_id", sa.String(50), nullable=False),
        sa.Column("jira_issue_type", sa.String(50), nullable=False),
        sa.Column(
            "bud_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bud_documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "bug_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("bugs.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(30), nullable=False, server_default="pending"),
        sa.Column("consolidated_into", sa.String(50), nullable=True),
        sa.Column("note", sa.Text, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
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
    op.create_unique_constraint(
        "uq_jira_issue_org",
        "jira_issue_bud_map",
        ["org_id", "jira_issue_key"],
    )
    op.create_index("ix_jira_map_session", "jira_issue_bud_map", ["import_session_id"])
    op.create_index("ix_jira_map_bud", "jira_issue_bud_map", ["bud_id"])
    op.create_index("ix_jira_map_bug", "jira_issue_bud_map", ["bug_id"])
    op.create_index(
        "ix_jira_map_org_status",
        "jira_issue_bud_map",
        ["org_id", "status"],
    )


def downgrade() -> None:
    op.drop_table("jira_issue_bud_map")
    op.drop_table("jira_import_sessions")
