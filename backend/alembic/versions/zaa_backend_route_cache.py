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

"""Add backend_route_cache table.

Mirrors the ``cluster_cache`` shape — SHA-keyed cache of HTTP route
declarations extracted from each backend repo's source. Written by the
new ``extract_routes`` per-repo stage on cache miss, read by the global
``backend_link`` phase.

Revision ID: zaa_backend_route_cache
Revises: zy_features_join_table
Create Date: 2026-05-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zaa_backend_route_cache"
down_revision: str | None = "zy_features_join_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create the cache table + supporting indexes."""
    op.create_table(
        "backend_route_cache",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "org_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("head_sha", sa.String(length=40), nullable=False),
        sa.Column("normalised_path", sa.String(length=500), nullable=False),
        sa.Column("http_method", sa.String(length=20), nullable=False),
        sa.Column("file_path", sa.String(length=1000), nullable=False),
        sa.Column(
            "indexed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "org_id",
            "repo_id",
            "head_sha",
            "normalised_path",
            "http_method",
            "file_path",
            name="uq_brc_repo_sha_route",
        ),
    )
    op.create_index("ix_brc_repo_sha", "backend_route_cache", ["repo_id", "head_sha"])


def downgrade() -> None:
    op.drop_index("ix_brc_repo_sha", table_name="backend_route_cache")
    op.drop_table("backend_route_cache")
