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

"""reposcanv2: drop unused repo_meta_communities + feature_meta_communities

Revision ID: zq_drop_meta_communities
Revises: b3549cc9d508
Create Date: 2026-04-27

The two meta-community tables and their PG enums were created speculatively
to support reduction-output caching and feature ↔ community provenance,
but no stage, MCP handler, or API surface ever wrote or read them. Dropping
to remove dead schema before it accretes data.

Forward-only intentionally — we don't recreate this on downgrade because
nothing in the live pipeline depends on these tables, and reviving them
later should rewrite the schema from scratch.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zq_drop_meta_communities"
down_revision: str | None = "b3549cc9d508"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_feature_meta_feature", table_name="feature_meta_communities")
    op.drop_index("ix_feature_meta_community", table_name="feature_meta_communities")
    op.drop_table("feature_meta_communities")
    op.drop_index(
        "ix_repo_meta_repo_sha_kept",
        table_name="repo_meta_communities",
        postgresql_where=sa.text("dropped = false"),
    )
    op.drop_index("ix_repo_meta_org_repo", table_name="repo_meta_communities")
    op.drop_table("repo_meta_communities")
    sa.Enum(name="feature_community_role").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="community_processing_status").drop(op.get_bind(), checkfirst=True)


def downgrade() -> None:
    raise NotImplementedError(
        "zq_drop_meta_communities is forward-only. To revive these tables, "
        "author a fresh migration that re-creates them with their final shape."
    )
