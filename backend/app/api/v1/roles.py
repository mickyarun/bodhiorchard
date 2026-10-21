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

from app.core.deps import PermissionSet, get_db, get_permission_set, require_permissions
from app.core.permission_deps import permissions_for_role
from app.models.role import Role, RoleScopeType
from app.models.user import User
from app.repositories.permission import PermissionRepository
from app.repositories.role import RoleRepository
from app.schemas.permission import PermissionCategoryRead, PermissionRead
from app.schemas.role import RoleCreate, RoleRead, RoleUpdate
from app.services.role_grants import (
    assert_can_grant,
    assert_can_grant_permission_ids,
    assert_can_manage_role,
    assignable_role_ids,
    log_sensitive_grant,
)
from app.services.role_validation import (
    assert_custom_role_name_allowed,
    assert_valid_base_role,
    read_or_404,
    with_inherited_workspace,
)

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
    user: User = Depends(require_permissions("team:view")),
    db: AsyncSession = Depends(get_db),
) -> list[RoleRead]:
    """List all active roles (system + this org's custom roles)."""
    return await RoleRepository(db, org_id=user.org_id).read_active()


@router.get("/roles/assignable", response_model=list[uuid.UUID])
async def list_assignable_roles(
    user: User = Depends(require_permissions("team:view")),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> list[uuid.UUID]:
    """Ids of the active roles the caller may give someone (the grant ceiling's answer)."""
    roles = await RoleRepository(db, org_id=user.org_id).list_active()
    return await assignable_role_ids(db, perms, roles)


@router.get("/roles/{role_id}", response_model=RoleRead)
async def get_role(
    role_id: uuid.UUID,
    user: User = Depends(require_permissions("team:view")),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Get a single role with its permissions."""
    return await read_or_404(RoleRepository(db, org_id=user.org_id), role_id)


@router.post("/roles", response_model=RoleRead, status_code=status.HTTP_201_CREATED)
async def create_role(
    body: RoleCreate,
    current_user: User = Depends(require_permissions("team:assign_roles")),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Create a custom org role.

    ``base_role_id`` must point at an ACTIVE SYSTEM role other than
    ``org_owner`` — the inheritance contract for phase auto-assignment.
    Anything else (custom role, inactive, missing, owner) is rejected with
    400. The caller can only include permissions they hold themselves.

    A role based on an engineering role inherits ``workspace:engineering``
    automatically, so a cloned "Senior Developer" isn't locked out of the
    platform because nobody ticked the workspace box.
    """
    role_repo = RoleRepository(db, org_id=current_user.org_id)
    assert_custom_role_name_allowed(body.name)
    await assert_valid_base_role(role_repo, body.base_role_id)
    # The base decides the member's effective role (and role-name checks
    # like tech-arch approval), so basing a role on one is a grant too.
    assert_can_grant(perms, await permissions_for_role(db, body.base_role_id))
    permission_ids = await with_inherited_workspace(db, body.base_role_id, body.permission_ids)
    granted = await assert_can_grant_permission_ids(db, perms, permission_ids)
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
        await role_repo.replace_permissions(role.id, permission_ids)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    log_sensitive_grant(
        actor_id=current_user.id,
        org_id=current_user.org_id,
        granted=granted,
        target=f"role:{role.id}",
    )
    return await read_or_404(role_repo, role.id)


@router.put("/roles/{role_id}", response_model=RoleRead)
async def update_role(
    role_id: uuid.UUID,
    body: RoleUpdate,
    current_user: User = Depends(require_permissions("team:assign_roles")),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> RoleRead:
    """Update a role's name, description, base_role_id, or permissions.

    System roles cannot be modified, and only this org's custom roles are
    visible. A new permission list may only contain permissions the
    caller holds.
    """
    role_repo = RoleRepository(db, org_id=current_user.org_id)
    role = await role_repo.get_by_id(role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.scope_type == RoleScopeType.SYSTEM:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be modified",
        )
    if role.id == current_user.role_id and not perms.is_owner:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You can't edit the role you hold. Ask another admin or the org owner.",
        )
    await assert_can_manage_role(db, actor=perms, role_id=role.id)

    if body.name is not None:
        assert_custom_role_name_allowed(body.name)
        role.name = body.name
    if body.description is not None:
        role.description = body.description
    if body.base_role_id is not None:
        await assert_valid_base_role(role_repo, body.base_role_id)
        # The base role decides the member's effective role (and with it
        # role-name checks like tech-arch approval), so re-basing is a grant.
        assert_can_grant(perms, await permissions_for_role(db, body.base_role_id))
        role.base_role_id = body.base_role_id

    if body.permission_ids is not None:
        granted = await assert_can_grant_permission_ids(db, perms, body.permission_ids)
        try:
            await role_repo.replace_permissions(role.id, body.permission_ids)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        log_sensitive_grant(
            actor_id=current_user.id,
            org_id=current_user.org_id,
            granted=granted,
            target=f"role:{role.id}",
        )

    await db.flush()
    return await read_or_404(role_repo, role.id)


@router.delete("/roles/{role_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_role(
    role_id: uuid.UUID,
    current_user: User = Depends(require_permissions("team:assign_roles")),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete one of this org's custom roles. System roles cannot be deleted."""
    role_repo = RoleRepository(db, org_id=current_user.org_id)
    role = await role_repo.get_by_id(role_id)
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")
    if role.scope_type == RoleScopeType.SYSTEM:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System roles cannot be deleted",
        )
    await assert_can_manage_role(db, actor=perms, role_id=role.id)
    await role_repo.delete(role)
