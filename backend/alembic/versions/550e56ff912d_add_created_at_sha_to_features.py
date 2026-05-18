"""add created_at_sha to features

Snaps the head_sha the reconciler was processing when a feature was
first inserted. Joined against ``pull_requests.merge_commit_sha`` by
the Features API to surface "Created by PR #N" alongside the row.
Old rows stay NULL — they predate this column and were all created
by baseline full scans (which the UI renders as "from baseline scan").

Revision ID: 550e56ff912d
Revises: zan_webhook_logs_replay_columns
Create Date: 2026-05-18 17:30:32.490966

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "550e56ff912d"
down_revision: str | None = "zan_webhook_logs_replay_columns"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "features",
        sa.Column("created_at_sha", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("features", "created_at_sha")
