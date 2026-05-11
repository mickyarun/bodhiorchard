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

"""Add composite indexes for optimized query patterns.

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-03-20 00:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create composite indexes matching repository query patterns."""
    # knowledge_items
    op.create_index("ix_ki_org_cat_active", "knowledge_items", ["org_id", "category", "is_active"])
    op.create_index(
        "ix_ki_org_cat_active_title",
        "knowledge_items",
        ["org_id", "category", "is_active", "title"],
    )
    op.create_index(
        "ix_ki_org_cat_active_source",
        "knowledge_items",
        ["org_id", "category", "is_active", "source"],
    )
    op.create_index(
        "ix_ki_org_cat_active_fstatus",
        "knowledge_items",
        ["org_id", "category", "is_active", "feature_status"],
    )
    op.create_index(
        "ix_ki_org_srcref_cat", "knowledge_items", ["org_id", "source_ref", "category"]
    )

    # bugs
    op.create_index("ix_bugs_org_status_created", "bugs", ["org_id", "status", "created_at"])

    # prd_documents
    op.create_index("ix_prd_org_status", "prd_documents", ["org_id", "status"])

    # organizations — partial index
    op.create_index(
        "ix_org_mcp_token_hash",
        "organizations",
        ["mcp_token_hash"],
        postgresql_where="mcp_token_hash IS NOT NULL",
    )

    # role_permissions
    op.create_index("ix_role_perms_role_id", "role_permissions", ["role_id"])

    # skill_profiles
    op.create_index("ix_sp_org_score", "skill_profiles", ["org_id", "skill_score"])


def downgrade() -> None:
    """Remove composite indexes."""
    op.drop_index("ix_sp_org_score", table_name="skill_profiles")
    op.drop_index("ix_role_perms_role_id", table_name="role_permissions")
    op.drop_index("ix_org_mcp_token_hash", table_name="organizations")
    op.drop_index("ix_prd_org_status", table_name="prd_documents")
    op.drop_index("ix_bugs_org_status_created", table_name="bugs")
    op.drop_index("ix_ki_org_srcref_cat", table_name="knowledge_items")
    op.drop_index("ix_ki_org_cat_active_fstatus", table_name="knowledge_items")
    op.drop_index("ix_ki_org_cat_active_source", table_name="knowledge_items")
    op.drop_index("ix_ki_org_cat_active_title", table_name="knowledge_items")
    op.drop_index("ix_ki_org_cat_active", table_name="knowledge_items")
