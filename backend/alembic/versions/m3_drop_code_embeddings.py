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

"""Drop unused code_embeddings table.

The CodeEmbedding model was never queried. Embeddings for knowledge
items live on the knowledge_items.embedding column instead.

Revision ID: m3_drop_code_embeddings
Revises: m2_remove_user_org_columns
Create Date: 2026-03-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m3_drop_code_embeddings"
down_revision: str | None = "m2_remove_user_org_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the code_embeddings table and its indexes."""
    op.execute("DROP INDEX IF EXISTS ix_code_embeddings_embedding")
    op.execute("DROP INDEX IF EXISTS ix_code_embeddings_org_id")
    op.drop_table("code_embeddings")


def downgrade() -> None:
    """Re-create the code_embeddings table."""
    op.create_table(
        "code_embeddings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
        ),
        sa.Column("file_path", sa.String(1000), nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("embedding", postgresql.ARRAY(sa.Float), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_code_embeddings_org_id", "code_embeddings", ["org_id"])
