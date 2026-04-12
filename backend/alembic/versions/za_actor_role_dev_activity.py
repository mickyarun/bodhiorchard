"""Add repo_path and actor_role columns to dev_activity_logs.

Adds two nullable columns to support the BUD detail testing-tab activity
stream and the untracked-repo "Add as tracked" CTA:

- ``repo_path``: raw filesystem path of the repo this activity came from.
  Persisted even when ``repo_id`` is NULL (i.e. the path doesn't match any
  tracked_repository), so the testing tab can group "untracked" rows by
  path. Backfilled to NULL for existing rows — historical untracked paths
  are not recoverable since they were never persisted.

- ``actor_role``: snapshot of the committer's OrgToUser.role at write time.
  Used by the BUD detail dev/testing tabs to route activity by role
  (testing tab filters role=qa, dev tab filters out qa). Snapshot at write
  time so role changes don't retroactively rewrite history. Backfilled
  best-effort from each user's CURRENT org role.

Also adds a composite index ``(bud_id, actor_role)`` to make the role-
filtered queries that drive both tabs efficient.

Revision ID: za_actor_role_dev_activity
Revises: 75212a109582
Create Date: 2026-04-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "za_actor_role_dev_activity"
down_revision: str | None = "75212a109582"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the two columns + composite index, then backfill actor_role."""
    op.add_column(
        "dev_activity_logs",
        sa.Column("repo_path", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "dev_activity_logs",
        sa.Column("actor_role", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_dev_activity_bud_role",
        "dev_activity_logs",
        ["bud_id", "actor_role"],
    )

    # Backfill actor_role from the user's CURRENT org_to_user.role.
    # Best-effort: rows where user_id IS NULL stay NULL (e.g. anonymous
    # webhook events), and rows whose user has since left the org also
    # stay NULL. Both fall through to the dev-tab default in the read
    # endpoint via the "actor_role IS NULL" branch of exclude_role.
    op.execute(
        """
        UPDATE dev_activity_logs d
        SET actor_role = m.role
        FROM org_to_user m
        WHERE d.user_id IS NOT NULL
          AND d.user_id = m.user_id
          AND d.org_id = m.org_id
        """
    )


def downgrade() -> None:
    """Drop the index and the two columns."""
    op.drop_index("ix_dev_activity_bud_role", table_name="dev_activity_logs")
    op.drop_column("dev_activity_logs", "actor_role")
    op.drop_column("dev_activity_logs", "repo_path")
