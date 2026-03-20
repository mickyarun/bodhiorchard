"""Add teams and team_members tables.

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-20 00:01:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str = "b2c3d4e5f6a7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Create teams and team_members tables."""
    op.create_table(
        "teams",
        sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column("org_id", sa.Uuid(), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("org_id", "name", name="uq_teams_org_name"),
    )
    op.create_index("ix_teams_org_id", "teams", ["org_id"])

    op.create_table(
        "team_members",
        sa.Column("id", sa.Uuid(), nullable=False, default=sa.text("gen_random_uuid()")),
        sa.Column(
            "team_id",
            sa.Uuid(),
            sa.ForeignKey("teams.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            sa.Uuid(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(20), nullable=False, server_default="member"),
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
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_members"),
    )
    op.create_index("ix_team_members_team_id", "team_members", ["team_id"])
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"])


def downgrade() -> None:
    """Drop teams and team_members tables."""
    op.drop_table("team_members")
    op.drop_table("teams")
