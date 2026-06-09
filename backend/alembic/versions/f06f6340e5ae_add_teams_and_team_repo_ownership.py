"""add teams and team-repo ownership

Revision ID: f06f6340e5ae
Revises: d8fa5f485b44
Create Date: 2026-06-08 22:41:08.445407

"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f06f6340e5ae"
down_revision: str | None = "d8fa5f485b44"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# ``postgresql.ENUM(create_type=False)`` so the type lands once via the
# explicit ``create()`` call in upgrade and is dropped once in
# downgrade. Plain ``sa.Enum`` inside ``op.create_table`` silently
# double-creates / leaks the type — see the
# ``project_alembic_enum_create_table`` memory.
team_status_enum = postgresql.ENUM("active", "archived", name="team_status", create_type=False)


def upgrade() -> None:
    team_status_enum.create(op.get_bind(), checkfirst=True)

    # ``(id, org_id)`` unique on ``tracked_repositories`` is the
    # composite-FK target for ``team_repos`` so a team's repo MUST
    # belong to the team's org. ``id`` alone is already unique (PK);
    # this constraint only adds the index PG requires.
    op.create_unique_constraint("uq_tracked_repo_id_org", "tracked_repositories", ["id", "org_id"])

    op.create_table(
        "teams",
        sa.Column("org_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", team_status_enum, nullable=False),
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
        sa.ForeignKeyConstraint(["org_id"], ["organizations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "org_id", name="uq_teams_id_org"),
        sa.UniqueConstraint("org_id", "name", name="uq_teams_org_name"),
    )
    op.create_index("ix_teams_org_status", "teams", ["org_id", "status"], unique=False)

    op.create_table(
        "team_members",
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
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
            ["team_id", "org_id"],
            ["teams.id", "teams.org_id"],
            name="fk_team_members_team_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id", "org_id"],
            ["org_to_user.user_id", "org_to_user.org_id"],
            name="fk_team_members_user_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_members_team_user"),
    )
    op.create_index("ix_team_members_user_id", "team_members", ["user_id"], unique=False)

    op.create_table(
        "team_repos",
        sa.Column("team_id", sa.UUID(), nullable=False),
        sa.Column("repo_id", sa.UUID(), nullable=False),
        sa.Column("org_id", sa.UUID(), nullable=False),
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
            ["team_id", "org_id"],
            ["teams.id", "teams.org_id"],
            name="fk_team_repos_team_org",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["repo_id", "org_id"],
            ["tracked_repositories.id", "tracked_repositories.org_id"],
            name="fk_team_repos_repo_org",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "repo_id", name="uq_team_repos_team_repo"),
    )
    op.create_index("ix_team_repos_repo_id", "team_repos", ["repo_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_team_repos_repo_id", table_name="team_repos")
    op.drop_table("team_repos")
    op.drop_index("ix_team_members_user_id", table_name="team_members")
    op.drop_table("team_members")
    op.drop_index("ix_teams_org_status", table_name="teams")
    op.drop_table("teams")

    op.drop_constraint("uq_tracked_repo_id_org", "tracked_repositories", type_="unique")

    team_status_enum.drop(op.get_bind(), checkfirst=True)
