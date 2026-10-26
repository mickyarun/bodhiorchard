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

"""Leave types on a policy. Types are deactivated, never deleted."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._leave_admin import load_policy, load_type, type_read
from app.core.deps import PermissionSet, get_db, get_permission_set, require_permissions
from app.models.user import User
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave_type import LeaveTypeRead, LeaveTypeWrite
from app.services.leave import type_admin, type_linking
from app.services.leave.permissions import APPROVE, CONFIGURE

router = APIRouter(tags=["leave-admin"])


@router.get("/policies/{policy_id}/types", response_model=list[LeaveTypeRead])
async def list_types(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveTypeRead]:
    """All types on a policy, active and inactive."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    types = await LeaveTypeRepository(db, org_id=current_user.org_id).list_for_policy(policy.id)
    return [type_read(t) for t in types]


@router.post(
    "/policies/{policy_id}/types",
    response_model=LeaveTypeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_type(
    policy_id: uuid.UUID,
    body: LeaveTypeWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeRead:
    """Add a leave type to a policy."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    created = await type_admin.create_type(
        db, policy, current_user.id, body, may_approve=perms.has(APPROVE)
    )
    return type_read(created)


@router.put("/types/{type_id}", response_model=LeaveTypeRead)
async def update_type(
    type_id: uuid.UUID,
    body: LeaveTypeWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeRead:
    """Edit a policy's own type. Quota changes apply to years not yet allocated.

    A type that follows the library is changed there, or via ``/link``.
    """
    leave_type = await load_type(db, current_user.org_id, type_id)
    await type_linking.update_own_type(
        db, leave_type, current_user.id, body, may_approve=perms.has(APPROVE)
    )
    return type_read(leave_type)
