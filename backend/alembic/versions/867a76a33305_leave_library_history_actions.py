"""leave library history actions

Revision ID: 867a76a33305
Revises: 6ac64e96babc
Create Date: 2026-10-22 16:52:08.260350

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "867a76a33305"
down_revision: str | None = "6ac64e96babc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add the library actions to leave_config_action.

    Autogenerate doesn't see new enum values. ADD VALUE can't be used in the
    transaction that adds it, and nothing here uses it.
    """
    for value in ("library_type_created", "library_type_updated", "library_type_deleted"):
        op.execute(f"ALTER TYPE leave_config_action ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    """Enum values can't be removed in Postgres; they stay, unused."""
