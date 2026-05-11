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

"""Add synthesized_features table — immutable pre-merge feature store.

Written once by the MCP ``write_feature_registry`` handler during
``FEATURE_SYNTHESIS``. Never mutated by merge (only ``merge_outcome``
is updated). Superseded rows get ``superseded_at`` set but are never
hard-deleted — this is the durable audit trail that makes bad-merge
recovery, per-feature merge visibility, and synthesis-queue self-heal
possible.

See ``BODHIORCHARD-ARCHITECTURE.md §18.12`` for how this table relates
to ``knowledge_items`` + ``knowledge_to_repo``.

Revision ID: zo_synthesized_features
Revises: zn_scan_phase_checkpoints
Create Date: 2026-04-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zo_synthesized_features"
down_revision: str | None = "zn_scan_phase_checkpoints"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_MERGE_OUTCOME_VALUES = ("canonical", "merged_into", "unvisited")


def upgrade() -> None:
    # Enum for the per-row merge outcome. Raw CREATE TYPE + create_type=False
    # on the column matches the asyncpg-safe pattern used elsewhere.
    merge_outcome_values = ", ".join(f"'{v}'" for v in _MERGE_OUTCOME_VALUES)
    op.execute(f"CREATE TYPE synth_feat_merge_outcome AS ENUM ({merge_outcome_values})")

    op.create_table(
        "synthesized_features",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("scan_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("feature_title", sa.String(500), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "capabilities",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "cluster_names",
            postgresql.ARRAY(sa.String()),
            nullable=False,
            server_default=sa.text("ARRAY[]::varchar[]"),
        ),
        sa.Column(
            "code_locations",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
        sa.Column(
            "knowledge_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "merge_outcome",
            postgresql.ENUM(
                *_MERGE_OUTCOME_VALUES,
                name="synth_feat_merge_outcome",
                create_type=False,
            ),
            nullable=True,
        ),
        sa.Column(
            "merged_into_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("synthesized_features.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "synthesized_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("superseded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # scan_id-only queries are served by ix_synth_feat_scan_repo via
    # leading-column match; no standalone single-column index needed.
    op.create_index(
        "ix_synth_feat_scan_repo",
        "synthesized_features",
        ["scan_id", "repo_id"],
    )
    op.create_index(
        "ix_synth_feat_repo_title",
        "synthesized_features",
        ["org_id", "repo_id", "feature_title"],
    )
    op.create_index(
        "ix_synth_feat_merged_into",
        "synthesized_features",
        ["merged_into_id"],
    )
    # Partial index powering the "current pre-merge view" query used by
    # FEATURE_MERGE snapshot and B2 queue self-heal. Restricting to
    # superseded_at IS NULL keeps the index small as history grows.
    op.create_index(
        "ix_synth_feat_latest",
        "synthesized_features",
        ["org_id", "repo_id"],
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.create_index(
        "ix_synth_feat_scan_outcome",
        "synthesized_features",
        ["scan_id", "merge_outcome"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_synth_feat_scan_outcome",
        table_name="synthesized_features",
    )
    op.drop_index(
        "ix_synth_feat_latest",
        table_name="synthesized_features",
        postgresql_where=sa.text("superseded_at IS NULL"),
    )
    op.drop_index(
        "ix_synth_feat_merged_into",
        table_name="synthesized_features",
    )
    op.drop_index(
        "ix_synth_feat_repo_title",
        table_name="synthesized_features",
    )
    op.drop_index("ix_synth_feat_scan_repo", table_name="synthesized_features")
    op.drop_table("synthesized_features")
    op.execute("DROP TYPE IF EXISTS synth_feat_merge_outcome")
