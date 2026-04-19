"""add user_mcp_tokens table and expand dev_activity_logs

Revision ID: 11d8392f4c09
Revises: 73bce4e5a843
Create Date: 2026-03-27 13:41:50.663558

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "11d8392f4c09"
down_revision: str | None = "73bce4e5a843"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create user_mcp_tokens and expand dev_activity_logs."""
    # ── user_mcp_tokens ──
    op.create_table(
        "user_mcp_tokens",
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "token_prefix",
            sa.String(16),
            nullable=False,
            server_default="",
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
        sa.ForeignKeyConstraint(
            ["org_id"],
            ["organizations.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_mcp_token_user_org",
        "user_mcp_tokens",
        ["user_id", "org_id"],
        unique=True,
    )
    op.create_index(
        "ix_user_mcp_token_prefix",
        "user_mcp_tokens",
        ["token_prefix"],
    )

    # ── expand dev_activity_logs ──

    # Make bud_id nullable (was non-nullable)
    op.alter_column(
        "dev_activity_logs",
        "bud_id",
        existing_type=sa.UUID(),
        nullable=True,
    )
    # Make status nullable
    op.alter_column(
        "dev_activity_logs",
        "status",
        existing_type=sa.String(50),
        nullable=True,
    )
    # Make message nullable
    op.alter_column(
        "dev_activity_logs",
        "message",
        existing_type=sa.Text(),
        nullable=True,
    )
    # Add new columns
    op.add_column(
        "dev_activity_logs",
        sa.Column("user_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "dev_activity_logs",
        sa.Column("repo_id", sa.UUID(), nullable=True),
    )
    op.add_column(
        "dev_activity_logs",
        sa.Column("session_id", sa.String(100), nullable=True),
    )
    op.add_column(
        "dev_activity_logs",
        sa.Column(
            "event_type",
            sa.String(50),
            nullable=True,
        ),
    )
    op.add_column(
        "dev_activity_logs",
        sa.Column("branch", sa.String(500), nullable=True),
    )
    op.add_column(
        "dev_activity_logs",
        sa.Column("commit_sha", sa.String(40), nullable=True),
    )
    op.add_column(
        "dev_activity_logs",
        sa.Column("file_path", sa.String(1000), nullable=True),
    )
    op.add_column(
        "dev_activity_logs",
        sa.Column("files_changed", sa.Text(), nullable=True),
    )

    # Backfill event_type for existing rows (they were MCP updates)
    op.execute("UPDATE dev_activity_logs SET event_type = 'mcp_update' WHERE event_type IS NULL")
    # Now make event_type non-nullable
    op.alter_column(
        "dev_activity_logs",
        "event_type",
        existing_type=sa.String(50),
        nullable=False,
    )

    # Foreign keys
    op.create_foreign_key(
        "fk_dev_activity_user_id",
        "dev_activity_logs",
        "users",
        ["user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_dev_activity_repo_id",
        "dev_activity_logs",
        "tracked_repositories",
        ["repo_id"],
        ["id"],
        ondelete="SET NULL",
    )

    # Indexes
    op.create_index(
        "ix_dev_activity_session_id",
        "dev_activity_logs",
        ["session_id"],
    )
    op.create_index(
        "ix_dev_activity_repo_id",
        "dev_activity_logs",
        ["repo_id"],
    )
    op.create_index(
        "ix_dev_activity_event_type",
        "dev_activity_logs",
        ["event_type"],
    )


def downgrade() -> None:
    """Revert: drop new columns/tables."""
    # Drop indexes
    op.drop_index("ix_dev_activity_event_type", "dev_activity_logs")
    op.drop_index("ix_dev_activity_repo_id", "dev_activity_logs")
    op.drop_index("ix_dev_activity_session_id", "dev_activity_logs")

    # Drop foreign keys
    op.drop_constraint(
        "fk_dev_activity_repo_id",
        "dev_activity_logs",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_dev_activity_user_id",
        "dev_activity_logs",
        type_="foreignkey",
    )

    # Drop new columns
    op.drop_column("dev_activity_logs", "files_changed")
    op.drop_column("dev_activity_logs", "file_path")
    op.drop_column("dev_activity_logs", "commit_sha")
    op.drop_column("dev_activity_logs", "branch")
    op.drop_column("dev_activity_logs", "event_type")
    op.drop_column("dev_activity_logs", "session_id")
    op.drop_column("dev_activity_logs", "repo_id")
    op.drop_column("dev_activity_logs", "user_id")

    # Restore non-nullable constraints
    op.alter_column(
        "dev_activity_logs",
        "message",
        existing_type=sa.Text(),
        nullable=False,
    )
    op.alter_column(
        "dev_activity_logs",
        "status",
        existing_type=sa.String(50),
        nullable=False,
    )
    op.alter_column(
        "dev_activity_logs",
        "bud_id",
        existing_type=sa.UUID(),
        nullable=False,
    )

    # Drop user_mcp_tokens
    op.drop_index(
        "ix_user_mcp_token_prefix",
        table_name="user_mcp_tokens",
    )
    op.drop_index(
        "ix_user_mcp_token_user_org",
        table_name="user_mcp_tokens",
    )
    op.drop_table("user_mcp_tokens")
