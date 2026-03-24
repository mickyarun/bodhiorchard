"""Add notifications table.

Revision ID: s9b0c1d2e3
Revises: r8a9b0c1d2
Create Date: 2026-03-21 12:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text
from sqlalchemy.dialects.postgresql import ENUM as PG_ENUM
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "s9b0c1d2e3"
down_revision: str = "r8a9b0c1d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create notifications table."""
    op.execute(
        text(
            "DO $$ BEGIN "
            "CREATE TYPE notification_type AS ENUM ('job_completed', 'job_failed'); "
            "EXCEPTION WHEN duplicate_object THEN NULL; "
            "END $$"
        )
    )

    op.create_table(
        "notifications",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "org_id",
            UUID(as_uuid=True),
            sa.ForeignKey("organizations.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "type",
            PG_ENUM("job_completed", "job_failed", name="notification_type", create_type=False),
            nullable=False,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("deep_link", sa.String(500), nullable=True),
        sa.Column("job_id", sa.String(36), nullable=True),
        sa.Column("job_type", sa.String(50), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("is_dismissed", sa.Boolean, nullable=False, server_default="false"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
    )

    op.create_index("ix_notif_user_read", "notifications", ["user_id", "is_read"])


def downgrade() -> None:
    """Drop notifications table."""
    op.drop_index("ix_notif_user_read", table_name="notifications")
    op.drop_table("notifications")
    sa.Enum(name="notification_type").drop(op.get_bind(), checkfirst=True)
