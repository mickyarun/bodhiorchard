"""Add settings:view/edit permissions to RBAC seed.

Backfills the ``settings:view`` and ``settings:edit`` permissions used by the
design-system and agent-skill routers, which were referenced by
``require_permissions(...)`` decorators but never registered in the seed.
Grants them to every system role per its scope.

Revision ID: zj_settings_perms
Revises: zi_claude_auth_mode
Create Date: 2026-04-22
"""

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa

from alembic import op

revision: str = "zj_settings_perms"
down_revision: str | None = "zi_claude_auth_mode"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_PERMS = [
    ("settings:view", "View Project Settings"),
    ("settings:edit", "Edit Project Settings"),
]

# System-role grants. org_owner holds "*" in the seed but wildcards are expanded
# at seed time, so existing DBs won't have rows for new permissions — we insert
# them explicitly below (see org_owner merge into the loop).
ROLE_GRANTS: dict[str, list[str]] = {
    "admin": ["settings:view", "settings:edit"],
    "pm": ["settings:view"],
    "tech_lead": ["settings:view", "settings:edit"],
    "manager": ["settings:view"],
    "developer": ["settings:view"],
    "designer": ["settings:view"],
    "qa": ["settings:view"],
}


def upgrade() -> None:
    conn = op.get_bind()

    cat_row = conn.execute(
        sa.text("SELECT id FROM permission_categories WHERE key = :key"),
        {"key": "SETTINGS"},
    ).fetchone()
    if cat_row is None:
        cat_id = str(uuid4())
        conn.execute(
            sa.text(
                "INSERT INTO permission_categories (id, name, key, description, display_order) "
                "VALUES (:id, :name, :key, :desc, :order)"
            ),
            {
                "id": cat_id,
                "name": "Project Settings",
                "key": "SETTINGS",
                "desc": "Permissions for project-level settings "
                "(design systems, agent skills, repos)",
                "order": 99,
            },
        )
    else:
        cat_id = str(cat_row[0])

    perm_ids: dict[str, str] = {}
    for order, (resource_id, display_name) in enumerate(NEW_PERMS):
        existing = conn.execute(
            sa.text("SELECT id FROM permissions WHERE resource_id = :rid"),
            {"rid": resource_id},
        ).fetchone()
        if existing is not None:
            perm_ids[resource_id] = str(existing[0])
            continue
        perm_id = str(uuid4())
        perm_ids[resource_id] = perm_id
        conn.execute(
            sa.text(
                "INSERT INTO permissions "
                "(id, name, resource_id, description, category_id, display_order) "
                "VALUES (:id, :name, :rid, NULL, :cat_id, :order)"
            ),
            {
                "id": perm_id,
                "name": display_name,
                "rid": resource_id,
                "cat_id": cat_id,
                "order": order,
            },
        )

    # Grant to all roles (system roles have org_id IS NULL). Org_owner holds
    # every permission via wildcard and is seeded row-by-row, so grant explicitly.
    for role_name, perm_slugs in {**ROLE_GRANTS, "org_owner": list(perm_ids.keys())}.items():
        role_row = conn.execute(
            sa.text("SELECT id FROM roles WHERE name = :name AND org_id IS NULL"),
            {"name": role_name},
        ).fetchone()
        if role_row is None:
            continue
        role_id = str(role_row[0])
        for slug in perm_slugs:
            perm_id = perm_ids[slug]
            conn.execute(
                sa.text(
                    "INSERT INTO role_permissions (id, role_id, permission_id) "
                    "VALUES (:id, :role_id, :perm_id) "
                    "ON CONFLICT ON CONSTRAINT uq_role_permissions_role_perm DO NOTHING"
                ),
                {"id": str(uuid4()), "role_id": role_id, "perm_id": perm_id},
            )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM permissions WHERE resource_id IN ('settings:view', 'settings:edit')")
    )
    conn.execute(sa.text("DELETE FROM permission_categories WHERE key = 'SETTINGS'"))
