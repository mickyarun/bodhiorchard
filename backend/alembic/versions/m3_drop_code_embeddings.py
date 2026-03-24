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
