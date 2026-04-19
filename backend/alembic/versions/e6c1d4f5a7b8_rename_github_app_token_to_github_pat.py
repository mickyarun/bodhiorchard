"""Rename github_app_token to github_pat on organizations.

Revision ID: e6c1d4f5a7b8
Revises: d5b0c3e4f6a7
Create Date: 2026-03-17 10:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e6c1d4f5a7b8"
down_revision: str | None = "d5b0c3e4f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Rename github_app_token column to github_pat."""
    op.alter_column(
        "organizations",
        "github_app_token",
        new_column_name="github_pat",
    )


def downgrade() -> None:
    """Revert github_pat back to github_app_token."""
    op.alter_column(
        "organizations",
        "github_pat",
        new_column_name="github_app_token",
    )
