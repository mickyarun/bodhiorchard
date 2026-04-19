"""Rename BUD statuses to pipeline model.

draft/planning → bud, designing → design, in_progress → development,
in_review → testing, ready/released → prod. Add uat, closed.

Revision ID: q7f8a9b0c1d2
Revises: p6e7f8a9b0c1
Create Date: 2026-03-20 23:45:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "q7f8a9b0c1d2"
down_revision: str = "p6e7f8a9b0c1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Old → new status mapping
_STATUS_MAP = {
    "draft": "bud",
    "planning": "bud",
    "designing": "design",
    "in_progress": "development",
    "in_review": "testing",
    "ready": "prod",
    "released": "prod",
    "discarded": "discarded",
}

_NEW_VALUES = ("bud", "design", "development", "testing", "uat", "prod", "closed", "discarded")

# Reverse mapping for downgrade (best-effort)
_REVERSE_MAP = {
    "bud": "draft",
    "design": "designing",
    "development": "in_progress",
    "testing": "in_review",
    "uat": "in_review",
    "prod": "released",
    "closed": "released",
    "discarded": "discarded",
}

_OLD_VALUES = (
    "draft",
    "planning",
    "designing",
    "in_progress",
    "in_review",
    "ready",
    "released",
    "discarded",
)


def upgrade() -> None:
    """Migrate bud_documents.status from old enum values to pipeline model."""
    # 1. Convert column to varchar to allow remapping
    op.alter_column(
        "bud_documents",
        "status",
        type_=sa.String(50),
        existing_type=sa.Enum(*_OLD_VALUES, name="bud_status"),
        existing_nullable=False,
        postgresql_using="status::text",
    )

    # 2. Drop the old enum type
    op.execute("DROP TYPE IF EXISTS bud_status")

    # 3. Remap values
    for old, new in _STATUS_MAP.items():
        op.execute(
            sa.text("UPDATE bud_documents SET status = :new WHERE status = :old").bindparams(
                new=new, old=old
            )
        )

    # 4. Create new enum type and apply
    new_enum = sa.Enum(*_NEW_VALUES, name="bud_status")
    new_enum.create(op.get_bind(), checkfirst=True)

    op.alter_column(
        "bud_documents",
        "status",
        type_=new_enum,
        existing_type=sa.String(50),
        existing_nullable=False,
        postgresql_using="status::bud_status",
    )


def downgrade() -> None:
    """Revert to old status enum values (best-effort)."""
    op.alter_column(
        "bud_documents",
        "status",
        type_=sa.String(50),
        existing_type=sa.Enum(*_NEW_VALUES, name="bud_status"),
        existing_nullable=False,
        postgresql_using="status::text",
    )

    op.execute("DROP TYPE IF EXISTS bud_status")

    for new, old in _REVERSE_MAP.items():
        op.execute(
            sa.text("UPDATE bud_documents SET status = :old WHERE status = :new").bindparams(
                old=old, new=new
            )
        )

    old_enum = sa.Enum(*_OLD_VALUES, name="bud_status")
    old_enum.create(op.get_bind(), checkfirst=True)

    op.alter_column(
        "bud_documents",
        "status",
        type_=old_enum,
        existing_type=sa.String(50),
        existing_nullable=False,
        postgresql_using="status::bud_status",
    )
