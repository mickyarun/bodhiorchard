"""Rename bud_status enum values from botanical to plain English.

Revision ID: n4c5d6e7f8a9
Revises: m3b4c5d6e7f8
Create Date: 2026-03-20 22:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "n4c5d6e7f8a9"
down_revision: str = "m3b4c5d6e7f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Mapping: old botanical names → new plain English names
_RENAMES = [
    ("seed", "draft"),
    ("sprout", "planning"),
    ("sapling", "designing"),
    ("growing", "in_progress"),
    ("budding", "in_review"),
    ("blooming", "ready"),
    ("fruiting", "released"),
    ("wilted", "discarded"),
]


def upgrade() -> None:
    """Rename bud_status enum values to plain English. Requires PostgreSQL 10+."""
    for old_val, new_val in _RENAMES:
        op.execute(f"ALTER TYPE bud_status RENAME VALUE '{old_val}' TO '{new_val}'")


def downgrade() -> None:
    """Revert to botanical names."""
    for old_val, new_val in _RENAMES:
        op.execute(f"ALTER TYPE bud_status RENAME VALUE '{new_val}' TO '{old_val}'")
