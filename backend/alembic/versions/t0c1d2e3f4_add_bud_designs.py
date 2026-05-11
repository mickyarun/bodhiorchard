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

"""Add bud_designs table for multi-repo design wireframes.

Revision ID: t0c1d2e3f4
Revises: s9b0c1d2e3
Create Date: 2026-03-21 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "t0c1d2e3f4"
down_revision: str | None = "s9b0c1d2e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create bud_designs table and migrate existing design_md rows."""
    op.create_table(
        "bud_designs",
        sa.Column(
            "id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "bud_id",
            UUID(as_uuid=True),
            sa.ForeignKey("bud_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repo_id", UUID(as_uuid=True), sa.ForeignKey("tracked_repositories.id"), nullable=True
        ),
        sa.Column("design_html", sa.Text, nullable=True),
        sa.Column("design_path", sa.String(500), nullable=True),
        sa.Column("notes", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="ready"),
        sa.Column("job_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("bud_id", "repo_id", name="uq_bud_design_bud_repo"),
    )
    op.create_index("ix_bud_designs_bud_id", "bud_designs", ["bud_id"])

    # Migrate existing design_md rows into bud_designs with repo_id=NULL
    op.execute(
        """
        INSERT INTO bud_designs (
            id, org_id, bud_id, repo_id, design_html,
            status, created_at, updated_at
        )
        SELECT gen_random_uuid(), org_id, id, NULL, design_md, 'ready', now(), now()
        FROM bud_documents
        WHERE design_md IS NOT NULL AND design_md != ''
        """
    )


def downgrade() -> None:
    """Drop bud_designs table."""
    op.drop_index("ix_bud_designs_bud_id", table_name="bud_designs")
    op.drop_table("bud_designs")
