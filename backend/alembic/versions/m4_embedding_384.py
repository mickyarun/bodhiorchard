"""Change embedding columns from Vector(768) to Vector(384).

Switching from Ollama nomic-embed-text (768d) to fastembed
BAAI/bge-small-en-v1.5 (384d). No data exists so columns are
dropped and re-added.

Revision ID: m4_embedding_384
Revises: m3_drop_code_embeddings
Create Date: 2026-03-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "m4_embedding_384"
down_revision: str | None = "m3_drop_code_embeddings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = [
    "knowledge_items",
    "bud_documents",
    "bugs",
    "enterprise_rules",
    "feature_learnings",
]


def upgrade() -> None:
    """Resize embedding columns from 768 to 384 dimensions."""
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding")
        op.execute(f"ALTER TABLE {table} ADD COLUMN embedding vector(384)")


def downgrade() -> None:
    """Resize embedding columns back to 768 dimensions."""
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DROP COLUMN IF EXISTS embedding")
        op.execute(f"ALTER TABLE {table} ADD COLUMN embedding vector(768)")
