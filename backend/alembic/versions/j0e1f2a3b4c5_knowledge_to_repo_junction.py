"""Replace knowledge_items.repo_id with knowledge_to_repo junction table.

Revision ID: j0e1f2a3b4c5
Revises: i9d0e1f2a3b4
Create Date: 2026-03-20 16:00:00.000000

"""

import uuid
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "j0e1f2a3b4c5"
down_revision: str | None = "i9d0e1f2a3b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create junction table and migrate existing repo_id links."""
    op.create_table(
        "knowledge_to_repo",
        sa.Column(
            "id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            primary_key=True,
            default=uuid.uuid4,
        ),
        sa.Column(
            "knowledge_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("knowledge_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "repo_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
    )
    op.create_unique_constraint(
        "uq_krl_knowledge_repo", "knowledge_to_repo", ["knowledge_id", "repo_id"]
    )
    op.create_index("ix_krl_knowledge_id", "knowledge_to_repo", ["knowledge_id"])
    op.create_index("ix_krl_repo_id", "knowledge_to_repo", ["repo_id"])

    # Migrate existing repo_id data into junction table
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "INSERT INTO knowledge_to_repo (id, knowledge_id, repo_id) "
            "SELECT gen_random_uuid(), id, repo_id "
            "FROM knowledge_items "
            "WHERE repo_id IS NOT NULL"
        )
    )

    # Drop the old repo_id column
    op.drop_index("ix_ki_repo_id", "knowledge_items")
    op.drop_constraint("knowledge_items_repo_id_fkey", "knowledge_items", type_="foreignkey")
    op.drop_column("knowledge_items", "repo_id")


def downgrade() -> None:
    """Restore repo_id column and drop junction table."""
    op.add_column(
        "knowledge_items",
        sa.Column(
            "repo_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "knowledge_items_repo_id_fkey",
        "knowledge_items",
        "tracked_repositories",
        ["repo_id"],
        ["id"],
    )
    op.create_index("ix_ki_repo_id", "knowledge_items", ["repo_id"])

    # Migrate back: pick one repo per knowledge item
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE knowledge_items ki "
            "SET repo_id = sub.repo_id "
            "FROM ("
            "  SELECT DISTINCT ON (knowledge_id) knowledge_id, repo_id "
            "  FROM knowledge_to_repo"
            ") sub "
            "WHERE ki.id = sub.knowledge_id"
        )
    )

    op.drop_index("ix_krl_repo_id", "knowledge_to_repo")
    op.drop_index("ix_krl_knowledge_id", "knowledge_to_repo")
    op.drop_constraint("uq_krl_knowledge_repo", "knowledge_to_repo")
    op.drop_table("knowledge_to_repo")
