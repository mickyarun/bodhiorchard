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

"""Add gitnexus_community_cache for fast extract-stage hydration.

The v2 ``extract`` stage runs a per-community cypher subprocess to fetch
each community's file list. On large repos (e.g. ATOAMerchantapp with
~2,360 communities) this fan-out, serialised by the global ``_NPX_LOCK``,
costs ~40 minutes of wall-clock time per scan — even when the SHA is
unchanged.

This table caches the (community_id, label, heuristic_label, symbol_count,
cohesion, files) tuple keyed on ``(repo_id, head_sha)`` so subsequent
extracts on the same SHA hydrate from Postgres in milliseconds and skip
the entire cypher fan-out. Rows are replaced wholesale on cache rebuild.

Revision ID: zs_gitnexus_community_cache
Revises: zr_synth_feat_tags
Create Date: 2026-04-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "zs_gitnexus_community_cache"
down_revision: str | None = "zr_synth_feat_tags"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "gitnexus_community_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
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
        sa.Column("head_sha", sa.String(40), nullable=False),
        sa.Column("community_id", sa.String(255), nullable=False),
        sa.Column("label", sa.String(500), nullable=False),
        sa.Column("heuristic_label", sa.String(500), nullable=True),
        sa.Column("symbol_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("cohesion", sa.Float(), nullable=True),
        sa.Column(
            "files",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "repo_id",
            "head_sha",
            "community_id",
            name="uq_gncc_repo_sha_community",
        ),
    )
    op.create_index(
        "ix_gncc_repo_sha",
        "gitnexus_community_cache",
        ["repo_id", "head_sha"],
    )


def downgrade() -> None:
    op.drop_index("ix_gncc_repo_sha", table_name="gitnexus_community_cache")
    op.drop_table("gitnexus_community_cache")
