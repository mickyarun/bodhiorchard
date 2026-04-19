"""seed rbac permissions

Revision ID: c4a9b2d3e5f6
Revises: b3f8a1c2d4e5
Create Date: 2026-03-17 10:30:00.000000

"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op
from app.core.permissions import DEFAULT_SYSTEM_ROLES, PERMISSION_CATEGORIES

# revision identifiers, used by Alembic.
revision: str = "c4a9b2d3e5f6"
down_revision: str | None = "b3f8a1c2d4e5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Seed permission categories, permissions, system roles, and mappings."""
    conn = op.get_bind()

    # 1. Insert permission categories
    category_ids: dict[str, str] = {}  # key -> uuid str
    for order, cat_def in enumerate(PERMISSION_CATEGORIES):
        cat_id = str(uuid4())
        category_ids[cat_def.key] = cat_id
        conn.execute(
            sa.text(
                "INSERT INTO permission_categories (id, name, key, description, display_order) "
                "VALUES (:id, :name, :key, :desc, :order)"
            ),
            {
                "id": cat_id,
                "name": cat_def.name,
                "key": cat_def.key,
                "desc": cat_def.description or None,
                "order": order,
            },
        )

    # 2. Insert permissions
    perm_ids: dict[str, str] = {}  # resource_id -> uuid str
    for cat_def in PERMISSION_CATEGORIES:
        cat_id = category_ids[cat_def.key]
        for order, perm_def in enumerate(cat_def.permissions):
            perm_id = str(uuid4())
            perm_ids[perm_def.resource_id] = perm_id
            conn.execute(
                sa.text(
                    "INSERT INTO permissions "
                    "(id, name, resource_id, description, category_id, display_order) "
                    "VALUES (:id, :name, :rid, :desc, :cat_id, :order)"
                ),
                {
                    "id": perm_id,
                    "name": perm_def.name,
                    "rid": perm_def.resource_id,
                    "desc": perm_def.description or None,
                    "cat_id": cat_id,
                    "order": order,
                },
            )

    # 3. Insert system roles and role-permission mappings
    for role_def in DEFAULT_SYSTEM_ROLES:
        role_id = str(uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO roles (id, name, description, org_id, scope_type, is_active) "
                "VALUES (:id, :name, :desc, NULL, 'system', true)"
            ),
            {
                "id": role_id,
                "name": role_def.name,
                "desc": role_def.description,
            },
        )

        for resource_id in role_def.permission_ids:
            perm_id = perm_ids.get(resource_id)
            if perm_id is None:
                continue
            rp_id = str(uuid4())
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, role_id, permission_id) "
                    "VALUES (:id, :role_id, :perm_id)"
                ),
                {"id": rp_id, "role_id": role_id, "perm_id": perm_id},
            )


def downgrade() -> None:
    """Remove all seeded RBAC data."""
    conn = op.get_bind()
    conn.execute(sa.text("DELETE FROM role_permissions"))
    conn.execute(sa.text("DELETE FROM roles WHERE scope_type = 'system'"))
    conn.execute(sa.text("DELETE FROM permissions"))
    conn.execute(sa.text("DELETE FROM permission_categories"))
