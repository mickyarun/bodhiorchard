"""drop setup_last_error debug column

Revision ID: 0e21a0b1f737
Revises: zal_tracked_repos_setup_err
Create Date: 2026-05-07

Reverts the DEBUG instrumentation column added in
``zal_tracked_repos_setup_err``. The chip-tooltip surfacing it powered
identified the prod failure (``Author identity unknown`` on the setup
commit, fixed by stamping ``-c user.email`` / ``-c user.name`` inline)
and is no longer needed.

Generated with ``alembic revision --autogenerate`` so the revision ID is
the standard 12-char hex hash (sidesteps the 32-char ``version_num`` cap
that broke the original migration's hand-named ID).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0e21a0b1f737"
down_revision: str | None = "zal_tracked_repos_setup_err"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("tracked_repositories", "setup_last_error")


def downgrade() -> None:
    op.add_column(
        "tracked_repositories",
        sa.Column("setup_last_error", sa.Text(), nullable=True),
    )
