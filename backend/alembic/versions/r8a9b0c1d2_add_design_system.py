"""Add design_system_refs table and bud design_md column.

Revision ID: r8a9b0c1d2
Revises: q7f8a9b0c1d2
Create Date: 2026-03-20 23:50:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "r8a9b0c1d2"
down_revision: str = "q7f8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create design_system_refs table and add design_md column to bud_documents."""
    # 1. Create design_system_refs table
    op.create_table(
        "design_system_refs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "repo_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tracked_repositories.id"),
            nullable=False,
        ),
        sa.Column("is_default", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("source_hash", sa.String(64), nullable=True),
        sa.Column(
            "extracted_at",
            sa.DateTime(timezone=True),
            nullable=False,
        ),
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
        sa.UniqueConstraint("org_id", "repo_id", name="uq_design_system_org_repo"),
    )

    # 2. Add design_md column to bud_documents
    op.add_column(
        "bud_documents",
        sa.Column("design_md", sa.Text, nullable=True),
    )


def downgrade() -> None:
    """Remove design_system_refs table and design_md column."""
    op.drop_column("bud_documents", "design_md")
    op.drop_table("design_system_refs")
