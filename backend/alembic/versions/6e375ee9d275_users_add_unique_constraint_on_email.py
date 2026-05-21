"""users: add unique constraint on email (partial, active only)

Revision ID: 6e375ee9d275
Revises: 555236b875ed
Create Date: 2026-05-21 13:49:24.345280

Why partial:

* Member-merge flow in ``app/api/v1/members.py::merge_members``
  soft-deletes the source by setting ``is_active = false`` and copies
  its primary email onto the target as an alias. The source row stays
  in ``users`` with its original ``email`` column intact, so a plain
  ``UNIQUE(email)`` would break post-merge: target and the
  soft-deleted source would both carry the same email.
* The intent of the constraint is to prevent a NEW signup (or a
  restored row) from colliding with an ACTIVE user. Restricting the
  index to ``WHERE is_active = TRUE`` matches that intent precisely.
* Postgres native syntax (``CREATE UNIQUE INDEX ... WHERE``) — no
  triggers needed.

Pre-flight: the upgrade refuses to run if duplicate emails exist among
currently-active users. Operators must dedupe first (see
``select email, count(*) from users where is_active=true group by 1
having count(*) > 1``).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "6e375ee9d275"
down_revision: str | None = "555236b875ed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the partial unique index, after asserting no active duplicates exist."""
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            SELECT email, COUNT(*) AS n
            FROM users
            WHERE is_active = TRUE
            GROUP BY email
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            f"Cannot add unique(email) index — active users still share email "
            f"{duplicate[0]!r} ({duplicate[1]} rows). Dedupe first."
        )
    op.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_users_email_active "
        "ON users (email) WHERE is_active = TRUE"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_users_email_active")
