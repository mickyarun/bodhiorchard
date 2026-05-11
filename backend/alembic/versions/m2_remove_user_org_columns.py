# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Remove org_id, role, role_id from users table.

Org membership is now tracked via org_to_user junction table.
Per-org roles live on org_to_user.role and org_to_user.role_id.

Revision ID: m2_remove_user_org_columns
Revises: m1_multi_org_prepare
Create Date: 2026-03-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "m2_remove_user_org_columns"
down_revision: str | None = "m1_multi_org_prepare"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Drop org_id, role, role_id columns from users and update constraints."""
    # Backfill org_to_user from users for any rows not yet migrated
    op.execute(
        """
        INSERT INTO org_to_user (id, user_id, org_id, role, role_id, created_at, updated_at)
        SELECT gen_random_uuid(), u.id, u.org_id, u.role, u.role_id, now(), now()
        FROM users u
        WHERE NOT EXISTS (
            SELECT 1 FROM org_to_user otu
            WHERE otu.user_id = u.id AND otu.org_id = u.org_id
        )
        """
    )

    # Copy role and role_id from users to existing org_to_user rows
    op.execute(
        """
        UPDATE org_to_user otu
        SET role = u.role, role_id = u.role_id
        FROM users u
        WHERE otu.user_id = u.id
        """
    )

    # Guard against duplicate emails before adding unique constraint
    op.execute(
        """
        DO $$ BEGIN
            IF EXISTS (SELECT email FROM users GROUP BY email HAVING count(*) > 1) THEN
                RAISE EXCEPTION 'Duplicate emails exist across orgs — manual merge required';
            END IF;
        END $$;
        """
    )

    # Drop old unique constraint (org_id, email)
    op.drop_constraint("uq_users_org_email", "users", type_="unique")

    # Add new global email uniqueness
    op.create_unique_constraint("uq_users_email", "users", ["email"])

    # Drop the org_id FK index
    op.drop_index("ix_users_org_id", table_name="users")

    # Drop columns
    op.drop_column("users", "org_id")
    op.drop_column("users", "role")
    op.drop_column("users", "role_id")


def downgrade() -> None:
    """Re-add org_id, role, role_id columns to users."""
    # Add columns as nullable first
    op.add_column(
        "users",
        sa.Column("role_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "users",
        sa.Column(
            "role",
            sa.Enum(
                "org_owner",
                "admin",
                "pm",
                "tech_lead",
                "developer",
                "designer",
                "qa",
                "manager",
                "support",
                "viewer",
                name="user_role",
            ),
            nullable=True,
        ),
    )
    op.add_column(
        "users",
        sa.Column("org_id", postgresql.UUID(as_uuid=True), nullable=True),
    )

    # Backfill from org_to_user (pick first membership per user)
    op.execute(
        """
        UPDATE users u
        SET org_id = otu.org_id, role = otu.role, role_id = otu.role_id
        FROM (
            SELECT DISTINCT ON (user_id) user_id, org_id, role, role_id
            FROM org_to_user
            ORDER BY user_id, created_at
        ) otu
        WHERE u.id = otu.user_id
        """
    )

    # Set defaults for any users without org_to_user rows
    op.execute("UPDATE users SET role = 'developer' WHERE role IS NULL")

    # Make columns non-nullable (org_id may still be NULL for orphans)
    op.alter_column("users", "role", nullable=False, server_default="developer")

    op.create_index("ix_users_org_id", "users", ["org_id"])
    op.drop_constraint("uq_users_email", "users", type_="unique")
    op.create_unique_constraint("uq_users_org_email", "users", ["org_id", "email"])
    op.create_foreign_key(None, "users", "organizations", ["org_id"], ["id"])
    op.create_foreign_key(None, "users", "roles", ["role_id"], ["id"])
