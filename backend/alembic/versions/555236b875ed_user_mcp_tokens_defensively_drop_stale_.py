"""user_mcp_tokens: defensively drop stale single-token unique

Revision ID: 555236b875ed
Revises: 9cebb2e45a3c
Create Date: 2026-05-21 13:41:49.587852

The original ``2c87d34be5bc`` migration was supposed to drop the legacy
``ix_user_mcp_token_user_org`` unique index (on ``(user_id, org_id)``)
when it introduced the multi-token-per-user model. On some databases —
typically those restored from a dump that pre-dated that migration but
were then stamped to head — the old index survived. The new
``ix_user_mcp_token_user_org_name`` exists alongside it, so the model
appears correct but inserting a second token for the same ``(user_id,
org_id)`` still raises a UniqueViolation against the leftover index.

This migration drops the stale index idempotently:

* On a clean DB (where the original drop ran) it is a no-op.
* On a drifted DB (where the original drop didn't run) it removes the
  legacy constraint and unblocks the multi-token endpoint.

``DROP INDEX IF EXISTS`` is raw SQL because Alembic's ``op.drop_index``
has no checkfirst kwarg and would error on the no-op path.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "555236b875ed"
down_revision: str | None = "9cebb2e45a3c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop the legacy ``(user_id, org_id)`` unique index if it lingers."""
    op.execute("DROP INDEX IF EXISTS ix_user_mcp_token_user_org")


def downgrade() -> None:
    """Restore the legacy unique constraint.

    Only safe when there is at most one row per ``(user_id, org_id)``;
    otherwise the CREATE will fail. Used in rollback rehearsals.
    """
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_user_mcp_token_user_org "
        "ON user_mcp_tokens (user_id, org_id)"
    )
