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

"""Add tracked_repositories table for explicit repo management.

Revision ID: g7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-03-20 14:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "g7b8c9d0e1f2"
down_revision: str | None = "f6a7b8c9d0e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create tracked_repositories table and migrate existing repo data."""
    # Create enum via raw SQL to avoid SQLAlchemy's double-creation issue
    # with asyncpg + create_table's before_create event.
    op.execute("CREATE TYPE repo_status AS ENUM ('active', 'ignored', 'removed')")

    op.create_table(
        "tracked_repositories",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
        ),
        sa.Column(
            "org_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("path", sa.String(1000), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column(
            "status",
            sa.String(10),
            nullable=False,
            server_default="active",
        ),
        sa.Column("head_sha", sa.String(40), nullable=True),
        sa.Column("last_scanned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("knowledge_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("feature_count", sa.Integer, nullable=False, server_default="0"),
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
    # Convert status column from varchar to the repo_status enum.
    # Done after create_table to avoid SQLAlchemy's before_create event
    # trying to re-create the enum type with asyncpg.
    op.execute("ALTER TABLE tracked_repositories ALTER COLUMN status DROP DEFAULT")
    op.execute(
        "ALTER TABLE tracked_repositories "
        "ALTER COLUMN status TYPE repo_status USING status::repo_status"
    )
    op.execute(
        "ALTER TABLE tracked_repositories ALTER COLUMN status SET DEFAULT 'active'::repo_status"
    )

    op.create_unique_constraint(
        "uq_tracked_repo_org_path", "tracked_repositories", ["org_id", "path"]
    )
    op.create_index(
        "ix_tracked_repo_org_status",
        "tracked_repositories",
        ["org_id", "status"],
    )

    # --- Data migration: insert existing repos from org.config ---
    conn = op.get_bind()
    orgs = conn.execute(sa.text("SELECT id, config FROM organizations WHERE config IS NOT NULL"))
    for org_id, config in orgs:
        if not config:
            continue
        repo_shas = (config.get("knowledge") or {}).get("repo_shas", {})
        for path, sha in repo_shas.items():
            name = path.rsplit("/", 1)[-1] if "/" in path else path
            conn.execute(
                sa.text(
                    "INSERT INTO tracked_repositories "
                    "(id, org_id, path, name, status, head_sha) "
                    "VALUES (:id, :org_id, :path, :name, 'active', :sha) "
                    "ON CONFLICT (org_id, path) DO NOTHING"
                ),
                {
                    "id": str(uuid.uuid4()),
                    "org_id": str(org_id),
                    "path": path,
                    "name": name,
                    "sha": sha,
                },
            )


def downgrade() -> None:
    """Drop tracked_repositories table."""
    op.drop_index("ix_tracked_repo_org_status")
    op.drop_constraint("uq_tracked_repo_org_path", "tracked_repositories")
    op.drop_table("tracked_repositories")
    op.execute("DROP TYPE IF EXISTS repo_status")
