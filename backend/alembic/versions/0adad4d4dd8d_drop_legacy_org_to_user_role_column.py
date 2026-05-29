"""drop legacy org_to_user.role column

Revision ID: 0adad4d4dd8d
Revises: 3a4087b1f022
Create Date: 2026-05-29 14:44:26.002988

The Members UI updates ``OrgToUser.role_id`` only and never refreshes the
legacy ``OrgToUser.role`` enum.  After this revision the canonical role is
resolved exclusively through ``OrgToUser.role_id → roles.name`` (with
``CUSTOM → base_role.name``).  The enum column and its underlying
``user_role`` Postgres type are dropped.

Upgrade order matters:
  1. Backfill ``role_id`` for any memberships still on the legacy enum so
     no user loses their role when the column goes away.
  2. Drop the column.
  3. Drop the ``user_role`` Postgres enum type that backed the column.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0adad4d4dd8d"
down_revision: str | None = "3a4087b1f022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Backfill: for memberships without a role_id, find the SYSTEM role
    # whose canonical name equals the legacy enum value and set role_id.
    # SYSTEM roles have org_id IS NULL and a globally unique name.
    op.execute(
        sa.text(
            """
            UPDATE org_to_user AS otu
            SET role_id = r.id
            FROM roles AS r
            WHERE otu.role_id IS NULL
              AND r.scope_type = 'system'
              AND r.name = otu.role::text
            """
        )
    )

    op.drop_column("org_to_user", "role")

    # Drop the now-orphaned Postgres enum type. Use IF EXISTS so an
    # environment that already dropped it manually doesn't break the
    # migration.
    op.execute(sa.text("DROP TYPE IF EXISTS user_role"))


def downgrade() -> None:
    # Recreate the enum type with the same set of labels the model had
    # at the moment this column was dropped.
    user_role = postgresql.ENUM(
        "org_owner",
        "admin",
        "pm",
        "tech_lead",
        "developer",
        "designer",
        "qa",
        "support",
        "viewer",
        "manager",
        name="user_role",
    )
    user_role.create(op.get_bind(), checkfirst=True)

    # Re-add the column nullable first so we can backfill before
    # enforcing NOT NULL.
    op.add_column(
        "org_to_user",
        sa.Column("role", user_role, nullable=True),
    )

    # Backfill the legacy column from the canonical role chain:
    # CUSTOM roles inherit through base_role; SYSTEM roles map directly.
    # Rows without a resolved canonical role default to 'developer' so
    # the NOT NULL re-add below succeeds.
    op.execute(
        sa.text(
            """
            UPDATE org_to_user AS otu
            SET role = COALESCE(
                CASE
                    WHEN r.scope_type = 'custom' THEN br.name
                    ELSE r.name
                END,
                'developer'
            )::user_role
            FROM roles AS r
            LEFT JOIN roles AS br ON br.id = r.base_role_id
            WHERE otu.role_id = r.id
            """
        )
    )
    # Any rows still NULL (role_id was NULL too) get the developer default.
    op.execute(sa.text("UPDATE org_to_user SET role = 'developer' WHERE role IS NULL"))

    op.alter_column("org_to_user", "role", nullable=False)
