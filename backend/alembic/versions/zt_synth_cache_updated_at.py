"""Add missing updated_at column to gitnexus_community_cache.

The original migration ``zs_gitnexus_community_cache`` declared
``created_at`` explicitly but missed ``updated_at`` — both come from
``TimestampMixin`` on ``BaseModel`` and SQLAlchemy generates SELECTs
that include both. Without the column the model can't be queried.

Revision ID: zt_synth_cache_updated_at
Revises: zs_gitnexus_community_cache
Create Date: 2026-04-28
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "zt_synth_cache_updated_at"
down_revision: str | None = "zs_gitnexus_community_cache"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "gitnexus_community_cache",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )


def downgrade() -> None:
    op.drop_column("gitnexus_community_cache", "updated_at")
