"""Add repo_id FK from knowledge_items to tracked_repositories.

Revision ID: h8c9d0e1f2a3
Revises: g7b8c9d0e1f2
Create Date: 2026-03-20 15:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "h8c9d0e1f2a3"
down_revision: str | None = "g7b8c9d0e1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add repo_id column and backfill from title prefix patterns."""
    op.add_column(
        "knowledge_items",
        sa.Column(
            "repo_id",
            sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("tracked_repositories.id"),
            nullable=True,
        ),
    )
    op.create_index("ix_ki_repo_id", "knowledge_items", ["repo_id"])

    # Backfill: match title prefix "[repo-name]" to tracked_repositories.name
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "UPDATE knowledge_items ki "
            "SET repo_id = tr.id "
            "FROM tracked_repositories tr "
            "WHERE ki.org_id = tr.org_id "
            "  AND ki.title LIKE '[' || tr.name || ']%' "
            "  AND ki.repo_id IS NULL"
        )
    )

    # For single-repo orgs, assign the sole tracked repo to unlinked items
    conn.execute(
        sa.text(
            "UPDATE knowledge_items ki "
            "SET repo_id = sub.repo_id "
            "FROM ("
            "  SELECT tr.org_id, tr.id AS repo_id "
            "  FROM tracked_repositories tr "
            "  WHERE tr.status != 'removed' "
            "    AND tr.org_id IN ("
            "      SELECT org_id FROM tracked_repositories "
            "      WHERE status != 'removed' "
            "      GROUP BY org_id HAVING COUNT(*) = 1"
            "    )"
            ") sub "
            "WHERE ki.org_id = sub.org_id "
            "  AND ki.repo_id IS NULL"
        )
    )


def downgrade() -> None:
    """Remove repo_id column."""
    op.drop_index("ix_ki_repo_id", "knowledge_items")
    op.drop_column("knowledge_items", "repo_id")
