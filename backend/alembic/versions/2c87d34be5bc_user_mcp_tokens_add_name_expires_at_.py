"""user_mcp_tokens: add name/expires_at/last_used_at, multi-token per user

Revision ID: 2c87d34be5bc
Revises: 303b6aac7141
Create Date: 2026-05-19 12:21:20.152362

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2c87d34be5bc"
down_revision: str | None = "303b6aac7141"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "user_mcp_tokens",
        sa.Column("name", sa.String(length=64), server_default="Default", nullable=False),
    )
    op.add_column(
        "user_mcp_tokens",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_mcp_tokens",
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.drop_index("ix_user_mcp_token_user_org", table_name="user_mcp_tokens")
    op.create_index(
        "ix_user_mcp_token_user_org_name",
        "user_mcp_tokens",
        ["user_id", "org_id", "name"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_user_mcp_token_user_org_name", table_name="user_mcp_tokens")
    op.create_index(
        "ix_user_mcp_token_user_org",
        "user_mcp_tokens",
        ["user_id", "org_id"],
        unique=True,
    )
    op.drop_column("user_mcp_tokens", "last_used_at")
    op.drop_column("user_mcp_tokens", "expires_at")
    op.drop_column("user_mcp_tokens", "name")
