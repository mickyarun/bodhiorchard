"""Idempotent seeder for permission categories, permissions, system roles, and mappings."""

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions import DEFAULT_SYSTEM_ROLES, PERMISSION_CATEGORIES
from app.models.permission import (
    Permission,
    PermissionCategory,
    Role,
    RolePermission,
    RoleScopeType,
)

logger = structlog.get_logger(__name__)


async def seed_permissions(db: AsyncSession) -> None:
    """Seed permission categories, permissions, system roles, and role-permission mappings.

    This function is idempotent — it skips records that already exist (matched by
    unique keys: category.key, permission.resource_id, role.name with org_id=NULL).

    Args:
        db: An active async database session. The caller is responsible for committing.
    """
    # 1. Seed permission categories
    category_map: dict[str, PermissionCategory] = {}
    for order, cat_def in enumerate(PERMISSION_CATEGORIES):
        result = await db.execute(
            select(PermissionCategory).where(PermissionCategory.key == cat_def.key)
        )
        category = result.scalar_one_or_none()
        if category is None:
            category = PermissionCategory(
                name=cat_def.name,
                key=cat_def.key,
                description=cat_def.description,
                display_order=order,
            )
            db.add(category)
            await db.flush()
            logger.info("seeded_permission_category", key=cat_def.key)
        category_map[cat_def.key] = category

    # 2. Seed permissions
    permission_map: dict[str, Permission] = {}
    for cat_def in PERMISSION_CATEGORIES:
        category = category_map[cat_def.key]
        for order, perm_def in enumerate(cat_def.permissions):
            result = await db.execute(
                select(Permission).where(Permission.resource_id == perm_def.resource_id)
            )
            perm = result.scalar_one_or_none()
            if perm is None:
                perm = Permission(
                    name=perm_def.name,
                    resource_id=perm_def.resource_id,
                    description=perm_def.description,
                    category_id=category.id,
                    display_order=order,
                )
                db.add(perm)
                await db.flush()
                logger.info("seeded_permission", resource_id=perm_def.resource_id)
            permission_map[perm_def.resource_id] = perm

    # 3. Seed system roles and role-permission mappings
    for role_def in DEFAULT_SYSTEM_ROLES:
        result = await db.execute(
            select(Role).where(Role.name == role_def.name, Role.org_id.is_(None))
        )
        role = result.scalar_one_or_none()
        if role is None:
            role = Role(
                name=role_def.name,
                description=role_def.description,
                org_id=None,
                scope_type=RoleScopeType.SYSTEM,
                is_active=True,
            )
            db.add(role)
            await db.flush()
            logger.info("seeded_role", name=role_def.name)

        # Sync role-permission mappings
        existing_result = await db.execute(
            select(RolePermission.permission_id).where(RolePermission.role_id == role.id)
        )
        existing_perm_ids = set(existing_result.scalars().all())

        for resource_id in role_def.permission_ids:
            perm = permission_map.get(resource_id)
            if perm is None:
                logger.warning(
                    "permission_not_found_for_role",
                    role=role_def.name,
                    resource_id=resource_id,
                )
                continue
            if perm.id not in existing_perm_ids:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))

        await db.flush()

    logger.info("permission_seed_complete")
