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

"""CRUD endpoints for roles and listing permissions."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permissions
from app.models.role import Role, RoleScopeType
from app.models.user import User
from app.repositories.permission import PermissionRepository
from app.repositories.role import RoleRepository
from app.schemas.permission import PermissionCategoryRead, PermissionRead
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate
from app.services.role_validation import assert_valid_base_role, read_or_404

router = APIRouter(tags=["roles"])


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
                PermissionRead(
                    id=p.id,
                    name=p.name,
                    resource_id=p.resource_id,
                    description=p.description,
                    category_key=cat.key,
                    display_order=p.display_order,
                )
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
    """List all active roles (system + org custom)."""
    return await RoleRepository(db).read_active()


@router.get("/roles/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: uuid.UUID,
    _user: User = Depends(require_permissions("team:view")),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Get a single role with its permissions."""
    return await read_or_404(RoleRepository(db), role_id)


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    current_user: User = Depends(require_permissions("team:assign_roles")),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Create a custom org role.

    ``base_role_id`` must point at an ACTIVE SYSTEM role — the
    inheritance contract for phase auto-assignment. Anything else
    (custom role, inactive, missing) is rejected with 400.
    """
    role_repo = RoleRepository(db)
    await assert_valid_base_role(role_repo, body.base_role_id)
    role = Role(
        name=body.name,
        description=body.description,
        org_id=current_user.org_id,
        scope_type=RoleScopeType.CUSTOM,
        is_active=True,
        base_role_id=body.base_role_id,
    )
    await role_repo.create(role)
    try:
        await role_repo.replace_permissions(role.id, body.permission_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    return await read_or_404(role_repo, role.id)


@router.put("/roles/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    _user: User = Depends(require_permissions("team:assign_roles")),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Update a role's name, description, base_role_id, or permissions.

    System roles cannot be modified.
    """
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
    if body.base_role_id is not None:
        await assert_valid_base_role(role_repo, body.base_role_id)
        role.base_role_id = body.base_role_id

    if body.permission_ids is not None:
        try:
            await role_repo.replace_permissions(role.id, body.permission_ids)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc

    await db.flush()
    return await read_or_404(role_repo, role.id)


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
