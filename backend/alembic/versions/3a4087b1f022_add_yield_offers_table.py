"""add yield_offers table

Revision ID: 3a4087b1f022
Revises: 022576f6a3c9
Create Date: 2026-05-27 17:44:54.184820

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3a4087b1f022"
down_revision: str | None = "022576f6a3c9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ``postgresql.ENUM`` with ``create_type=False`` reliably suppresses
    # the inline CREATE TYPE that ``op.create_table`` would otherwise
    # emit — the generic ``sa.Enum`` form ignores the flag for
    # ``create_table``. We create the type explicitly first, then
    # reference it via the dialect-specific Enum in the column.
    yield_offer_status = postgresql.ENUM(
        "pending",
        "accepted",
        "rejected",
        "expired",
        name="yield_offer_status",
        create_type=False,
    )
    yield_offer_status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "yield_offers",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("incoming_bud_id", sa.UUID(), nullable=False),
        sa.Column("yieldable_bud_id", sa.UUID(), nullable=False),
        sa.Column("target_user_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            yield_offer_status,
            server_default="pending",
            nullable=False,
        ),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["incoming_bud_id"], ["bud_documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["yieldable_bud_id"], ["bud_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_yield_offer_incoming_bud", "yield_offers", ["incoming_bud_id"], unique=False
    )
    op.create_index(
        "ix_yield_offer_target_pending",
        "yield_offers",
        ["target_user_id", "status"],
        unique=False,
    )
    op.create_index(op.f("ix_yield_offers_org_id"), "yield_offers", ["org_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_yield_offers_org_id"), table_name="yield_offers")
    op.drop_index("ix_yield_offer_target_pending", table_name="yield_offers")
    op.drop_index("ix_yield_offer_incoming_bud", table_name="yield_offers")
    op.drop_table("yield_offers")
    postgresql.ENUM(name="yield_offer_status").drop(op.get_bind(), checkfirst=True)
