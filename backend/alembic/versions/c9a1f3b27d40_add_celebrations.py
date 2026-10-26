"""celebration opt-outs, ledger, settings audit trail, and self-hosted avatars

Revision ID: c9a1f3b27d40
Revises: 867a76a33305
Create Date: 2026-10-22 10:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c9a1f3b27d40"
down_revision: str | None = "867a76a33305"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUS = postgresql.ENUM(
    "claimed",
    "sent",
    "failed",
    "unknown",
    name="celebration_post_status",
    create_type=False,
)
_ACTION = postgresql.ENUM(
    "enabled",
    "disabled",
    "channel_changed",
    "updated",
    name="celebration_config_action",
    create_type=False,
)


def _timestamps() -> tuple[sa.Column[object], sa.Column[object]]:
    """``created_at`` / ``updated_at`` exactly as ``TimestampMixin`` declares them."""
    return (
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
    )


def upgrade() -> None:
    # ``ALTER TABLE users`` / ``employee_profiles`` take a brief ACCESS
    # EXCLUSIVE lock. Without a timeout that lock request queues behind any
    # long-running transaction and, while queued, blocks every login and
    # profile read behind it. Fail fast instead and let the deploy retry.
    op.execute("SET LOCAL lock_timeout = '5s'")

    # Opt-out model: existing rows become celebratable immediately, which is
    # why both columns ship with a server_default rather than a backfill.
    # A constant default makes these metadata-only on Postgres 11+.
    op.add_column(
        "employee_profiles",
        sa.Column(
            "celebrate_birthday",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )
    op.add_column(
        "employee_profiles",
        sa.Column(
            "celebrate_anniversary",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
    )

    # Self-hosted profile photos; both NULL for Slack-CDN avatars.
    op.add_column(
        "users",
        sa.Column("avatar_storage_path", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column("avatar_key", sa.String(length=32), nullable=True),
    )
    op.create_index("ix_users_avatar_key", "users", ["avatar_key"], unique=True)

    _STATUS.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "celebration_posts",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("celebrate_date", sa.Date(), nullable=False),
        sa.Column("slack_channel_id", sa.String(length=50), nullable=True),
        sa.Column("slack_message_ts", sa.String(length=50), nullable=True),
        sa.Column("birthday_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("anniversary_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("status", _STATUS, nullable=False, server_default="claimed"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("last_error", sa.String(length=200), nullable=True),
        sa.Column(
            "covered_dates",
            postgresql.ARRAY(sa.Date()),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        *_timestamps(),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.UniqueConstraint("org_id", "celebrate_date", name="uq_celebration_posts_org_date"),
    )
    op.create_index("ix_celebration_posts_org_id", "celebration_posts", ["org_id"])

    _ACTION.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "celebration_config_events",
        sa.Column("id", sa.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.UUID(as_uuid=True), nullable=False),
        sa.Column("action", _ACTION, nullable=False),
        sa.Column("changes", postgresql.JSONB(), nullable=False),
        *_timestamps(),
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.ForeignKeyConstraint(["actor_id"], ["users.id"], ondelete="RESTRICT"),
    )
    op.create_index(
        "ix_celebration_config_events_org",
        "celebration_config_events",
        ["org_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_celebration_config_events_org", table_name="celebration_config_events")
    op.drop_table("celebration_config_events")
    _ACTION.drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_celebration_posts_org_id", table_name="celebration_posts")
    op.drop_table("celebration_posts")
    _STATUS.drop(op.get_bind(), checkfirst=True)
    op.drop_index("ix_users_avatar_key", table_name="users")
    op.drop_column("users", "avatar_key")
    op.drop_column("users", "avatar_storage_path")
    op.drop_column("employee_profiles", "celebrate_anniversary")
    op.drop_column("employee_profiles", "celebrate_birthday")
