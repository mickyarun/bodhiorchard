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

"""Dedupe + partial unique index on feature_registry knowledge items.

Two active ``feature_registry`` rows with the same ``(org_id, title)``
caused ``KnowledgeItemRepository.get_by_title_and_category`` (which uses
``scalar_one_or_none``) to raise ``MultipleResultsFound`` and crash the
``merge_features`` MCP tool mid-scan.

This migration:

1. Soft-deactivates duplicate active rows, keeping only the OLDEST row
   per ``(org_id, title)`` pair (preserves FK links, embeddings, and
   repo associations on the survivor — which the scan pipeline would
   have merged into the survivor anyway via ``merge_features``).
2. Creates a partial unique index so the data-integrity guarantee is
   enforced at the DB level going forward.

Revision ID: zm_feature_registry_unique
Revises: zl_revert_sweeper
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zm_feature_registry_unique"
down_revision: str | None = "zl_revert_sweeper"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Deactivate duplicates — keep oldest active per (org_id, title).
    # Uses a window function on created_at so ties are broken
    # deterministically. Safe to re-run (idempotent): rows already
    # ``is_active=false`` are untouched by the WHERE clause.
    op.execute(
        sa.text(
            """
            WITH ranked AS (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY org_id, title
                           ORDER BY created_at ASC, id ASC
                       ) AS rn
                FROM knowledge_items
                WHERE category = 'feature_registry'
                  AND is_active = true
            )
            UPDATE knowledge_items
            SET is_active = false
            WHERE id IN (SELECT id FROM ranked WHERE rn > 1);
            """
        )
    )

    # Partial unique index — applies only to active feature_registry rows,
    # so soft-deleted duplicates can coexist (required: merge history
    # retains inactive tombstones under the same title).
    op.create_index(
        "uq_ki_org_title_feature_active",
        "knowledge_items",
        ["org_id", "title"],
        unique=True,
        postgresql_where=sa.text("category = 'feature_registry' AND is_active = true"),
    )


def downgrade() -> None:
    # Drop the unique guard. We deliberately do NOT reactivate the
    # deduped rows — the scan pipeline would have merged them on the
    # next run anyway, and bringing them back would immediately
    # re-trigger the original crash.
    op.drop_index(
        "uq_ki_org_title_feature_active",
        table_name="knowledge_items",
        postgresql_where=sa.text("category = 'feature_registry' AND is_active = true"),
    )
