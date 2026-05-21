"""add mcp_audit_log table

Revision ID: 29fbe5000c91
Revises: 2c87d34be5bc
Create Date: 2026-05-19 12:28:20.591579

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "29fbe5000c91"
down_revision: str | None = "2c87d34be5bc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "mcp_audit_log",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=True),
        sa.Column("token_id", sa.UUID(), nullable=True),
        sa.Column("tool_name", sa.String(length=64), nullable=False),
        sa.Column("transport", sa.String(length=16), nullable=False),
        sa.Column("ip", sa.String(length=64), nullable=True),
        sa.Column("user_agent", sa.String(length=256), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=False),
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
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["token_id"], ["user_mcp_tokens.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mcp_audit_created", "mcp_audit_log", ["created_at"], unique=False)
    op.create_index(
        "ix_mcp_audit_org_created",
        "mcp_audit_log",
        ["org_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_mcp_audit_token_created",
        "mcp_audit_log",
        ["token_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_mcp_audit_token_created", table_name="mcp_audit_log")
    op.drop_index("ix_mcp_audit_org_created", table_name="mcp_audit_log")
    op.drop_index("ix_mcp_audit_created", table_name="mcp_audit_log")
    op.drop_table("mcp_audit_log")
