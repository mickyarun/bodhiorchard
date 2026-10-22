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

"""The org's leave type library, and linking policy types to it (leave:configure)."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._leave_admin import load_policy, load_type, type_read
from app.core.deps import PermissionSet, get_db, get_permission_set, require_permissions
from app.models.user import User
from app.schemas.leave_library import (
    LibraryTypeAdd,
    LibraryTypeRead,
    LibraryTypeWrite,
    LinkedTypeWrite,
)
from app.schemas.leave_type import LeaveTypeRead
from app.services.leave import type_library, type_linking
from app.services.leave.permissions import APPROVE, CONFIGURE

router = APIRouter(tags=["leave-admin"])


@router.get("/library-types", response_model=list[LibraryTypeRead])
async def list_library(
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> list[LibraryTypeRead]:
    """Every library type, with the policies that use it."""
    return await type_library.list_library(db, current_user.org_id)


@router.post("/library-types", response_model=LibraryTypeRead, status_code=status.HTTP_201_CREATED)
async def create_library_type(
    body: LibraryTypeWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LibraryTypeRead:
    """Add a type to the library."""
    template = await type_library.create_entry(
        db, current_user.org_id, body, may_approve=perms.has(APPROVE)
    )
    return type_library.library_read(template, [])


@router.put("/library-types/{template_id}", response_model=LibraryTypeRead)
async def update_library_type(
    template_id: uuid.UUID,
    body: LibraryTypeWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LibraryTypeRead:
    """Edit a library type and every policy type that follows it."""
    template = await type_linking.load_entry(db, current_user.org_id, template_id)
    await type_library.update_entry(
        db, template, current_user.id, body, may_approve=perms.has(APPROVE)
    )
    return type_library.library_read(template, await type_library.uses_of(db, template))


@router.post(
    "/policies/{policy_id}/library-types",
    response_model=LeaveTypeRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_library_type(
    policy_id: uuid.UUID,
    body: LibraryTypeAdd,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeRead:
    """Add a library type to a policy, with the default or its own quota."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    template = await type_linking.load_entry(db, current_user.org_id, body.template_id)
    created = await type_linking.add_to_policy(
        db, policy, current_user.id, template, body, may_approve=perms.has(APPROVE)
    )
    return type_read(created)


@router.post("/types/{type_id}/link", response_model=LeaveTypeRead)
async def link_type(
    type_id: uuid.UUID,
    body: LibraryTypeAdd,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeRead:
    """Make a policy's own type follow a library type; its history stays."""
    leave_type = await load_type(db, current_user.org_id, type_id)
    template = await type_linking.load_entry(db, current_user.org_id, body.template_id)
    await type_linking.link_existing(
        db, leave_type, current_user.id, template, body, may_approve=perms.has(APPROVE)
    )
    return type_read(leave_type)


@router.put("/types/{type_id}/link", response_model=LeaveTypeRead)
async def update_link(
    type_id: uuid.UUID,
    body: LinkedTypeWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeRead:
    """Set a linked type's own quota on this policy, or switch it off."""
    leave_type = await load_type(db, current_user.org_id, type_id)
    await type_linking.update_linked(
        db, leave_type, current_user.id, body, may_approve=perms.has(APPROVE)
    )
    return type_read(leave_type)


@router.delete("/types/{type_id}/link", response_model=LeaveTypeRead)
async def unlink_type(
    type_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeRead:
    """Stop following the library; the type keeps its rules as the policy's own."""
    leave_type = await load_type(db, current_user.org_id, type_id)
    await type_linking.unlink(db, leave_type, current_user.id, may_approve=perms.has(APPROVE))
    return type_read(leave_type)
