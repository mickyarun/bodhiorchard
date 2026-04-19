# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""CRUD endpoints for roles and listing permissions."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permissions
from app.models.permission import (
    Permission,
    Role,
    RoleScopeType,
)
from app.models.user import User
from app.repositories.permission import PermissionRepository
from app.repositories.role import RoleRepository
from app.schemas.permission import (
    PermissionCategoryRead,
    PermissionRead,
    RoleCreate,
    RoleRead,
    RoleUpdate,
)

router = APIRouter(tags=["roles"])


def _permission_to_read(perm: Permission) -> PermissionRead:
    """Convert a Permission ORM instance to its read schema."""
    return PermissionRead(
        id=perm.id,
        name=perm.name,
        resource_id=perm.resource_id,
        description=perm.description,
        category_key=perm.category.key,
        display_order=perm.display_order,
    )


def _role_to_read(role: Role) -> RoleRead:
    """Convert a Role ORM instance (with loaded role_permissions) to its read schema."""
    return RoleRead(
        id=role.id,
        name=role.name,
        description=role.description,
        scope_type=role.scope_type.value,
        is_active=role.is_active,
        permissions=[_permission_to_read(rp.permission) for rp in role.role_permissions],
    )


@router.get("/permissions", response_model=list[PermissionCategoryRead])
async def list_permissions(
    _user: User = Depends(require_permissions("team:view")),
    db: AsyncSession = Depends(get_db),
) -> list[PermissionCategoryRead]:
    """List all permission categories with their nested permissions."""
    perm_repo = PermissionRepository(db)
    categories = await perm_repo.list_categories_ordered()

    return [
        PermissionCategoryRead(
            key=cat.key,
            name=cat.name,
            description=cat.description,
            display_order=cat.display_order,
            permissions=[
                _permission_to_read(p)
                for p in sorted(cat.permissions, key=lambda x: x.display_order)
            ],
        )
        for cat in categories
    ]


@router.get("/roles", response_model=list[RoleRead])
async def list_roles(
    _user: User = Depends(require_permissions("team:view")),
    db: AsyncSession = Depends(get_db),
) -> list[RoleRead]:
    """List all roles (system + org custom)."""
    role_repo = RoleRepository(db)
    roles = await role_repo.list_active()
    return [_role_to_read(r) for r in roles]


@router.get("/roles/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: uuid.UUID,
    _user: User = Depends(require_permissions("team:view")),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Get a single role with its permissions."""
    role_repo = RoleRepository(db)
    role = await role_repo.get_by_id(role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    return _role_to_read(role)


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    current_user: User = Depends(require_permissions("team:assign_roles")),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Create a custom org role."""
    role_repo = RoleRepository(db)
    role = Role(
        name=body.name,
        description=body.description,
        org_id=current_user.org_id,
        scope_type=RoleScopeType.CUSTOM,
        is_active=True,
    )
    await role_repo.create(role)

    # Validate and attach permissions
    try:
        await role_repo.replace_permissions(role.id, body.permission_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    await db.refresh(role)
    return _role_to_read(role)


@router.put("/roles/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    _user: User = Depends(require_permissions("team:assign_roles")),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Update a role's name, description, or permissions. System roles cannot be modified."""
    role_repo = RoleRepository(db)
    role = await role_repo.get_by_id(role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.scope_type == RoleScopeType.SYSTEM:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be modified",
        )

    if body.name is not None:
        role.name = body.name
    if body.description is not None:
        role.description = body.description

    if body.permission_ids is not None:
        try:
            await role_repo.replace_permissions(role.id, body.permission_ids)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    await db.flush()
    await db.refresh(role)
    return _role_to_read(role)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    _user: User = Depends(require_permissions("team:assign_roles")),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a custom role. System roles cannot be deleted."""
    role_repo = RoleRepository(db)
    role = await role_repo.get_by_id(role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.scope_type == RoleScopeType.SYSTEM:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be deleted",
        )
    await role_repo.delete(role)
