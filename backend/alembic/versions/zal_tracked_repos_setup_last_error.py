"""tracked_repositories: add setup_last_error (DEBUG)

Revision ID: zal_tracked_repos_setup_last_error
Revises: zak_org_github_app_slug
Create Date: 2026-05-07

DEBUG: surfaces ``commit_and_push_setup_worktree`` stderr to the frontend
chip tooltip so prod operators can see why a row is stuck in "Setup pending"
without grepping backend logs. Cleared on the next successful push.

This column (and the surrounding plumbing) is intentionally short-lived —
remove it once the setup-PR push path is reliably working in prod.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zal_tracked_repos_setup_last_error"
down_revision: str | None = "zak_org_github_app_slug"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tracked_repositories",
        sa.Column("setup_last_error", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tracked_repositories", "setup_last_error")
