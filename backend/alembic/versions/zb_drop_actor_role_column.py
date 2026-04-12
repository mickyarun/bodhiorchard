"""Drop actor_role column from dev_activity_logs.

The previous migration ``za_actor_role_dev_activity`` added a snapshotted
``actor_role`` column that was populated at write time from
``OrgToUser.role`` (the legacy enum). But the canonical RBAC path in this
codebase writes role assignments to ``OrgToUser.role_id → Role.name`` and
leaves the enum untouched — see ``backend/app/api/v1/members.py:211``,
which sets ``membership.role_id`` but never ``membership.role``.

Snapshotting the stale enum gave every user ``actor_role='developer'``
regardless of their real role, breaking the testing-tab routing.

The fix is to compute effective role at READ time by joining through
``org_to_user → roles``. This eliminates the drift entirely — role
changes made via the Members API propagate to the testing/dev tabs
immediately, no backfill ever needed.

The column was only live for a few hours; dropping it is safe.

Revision ID: zb_drop_actor_role_column
Revises: zb_bud_release_tracking
Create Date: 2026-04-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zb_drop_actor_role_column"
down_revision: str | None = "zb_bud_release_tracking"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the snapshotted actor_role column and its composite index."""
    op.drop_index("ix_dev_activity_bud_role", table_name="dev_activity_logs")
    op.drop_column("dev_activity_logs", "actor_role")


def downgrade() -> None:
    """Recreate the column and index (nullable, no backfill)."""
    op.add_column(
        "dev_activity_logs",
        sa.Column("actor_role", sa.String(length=50), nullable=True),
    )
    op.create_index(
        "ix_dev_activity_bud_role",
        "dev_activity_logs",
        ["bud_id", "actor_role"],
    )
