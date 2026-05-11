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

"""Add code_review status, bud_commits table, and repo branch columns.

Revision ID: z4_add_code_review_and_commits
Revises: z3_add_skill_model_effort
Create Date: 2026-03-23 14:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "z4_add_code_review_and_commits"
down_revision: str = "z3_add_skill_model_effort"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add code_review enum value, bud_commits table, and branch columns."""
    # 1. Add 'code_review' to bud_status enum (must run outside transaction —
    #    PostgreSQL requires ALTER TYPE ADD VALUE outside a transaction block)
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE bud_status ADD VALUE IF NOT EXISTS 'code_review' AFTER 'development'"
        )

    # 2. Create bud_commits table
    op.create_table(
        "bud_commits",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", UUID(as_uuid=True), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column(
            "bud_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bud_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("repo_path", sa.String(1000), nullable=False),
        sa.Column("branch_name", sa.String(500), nullable=False),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column("commit_message", sa.String(500), nullable=False),
        sa.Column("files_changed", sa.String(5000), nullable=False, server_default=""),
        sa.Column(
            "committed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("org_id", "commit_sha", name="uq_bud_commit_org_sha"),
    )
    op.create_index("ix_bud_commit_bud_id", "bud_commits", ["bud_id"])
    op.create_index("ix_bud_commit_org_repo", "bud_commits", ["org_id", "repo_path"])

    # 3. Add branch columns to tracked_repositories
    op.add_column(
        "tracked_repositories",
        sa.Column("main_branch", sa.String(100), nullable=True),
    )
    op.add_column(
        "tracked_repositories",
        sa.Column("develop_branch", sa.String(100), nullable=True),
    )


def downgrade() -> None:
    """Remove bud_commits table, branch columns. Enum value cannot be removed."""
    op.drop_column("tracked_repositories", "develop_branch")
    op.drop_column("tracked_repositories", "main_branch")
    op.drop_index("ix_bud_commit_org_repo", table_name="bud_commits")
    op.drop_index("ix_bud_commit_bud_id", table_name="bud_commits")
    op.drop_table("bud_commits")
