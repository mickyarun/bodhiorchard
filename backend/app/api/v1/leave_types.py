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

from app.api.v1._leave_admin import load_policy
from app.core.deps import get_db, require_permissions
from app.models.leave_type import LeaveType
from app.models.user import User
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave_policy import LeaveTypeRead, LeaveTypeWrite
from app.services.leave import type_admin
from app.services.leave.errors import LeaveNotFoundError
from app.services.leave.permissions import CONFIGURE

router = APIRouter(tags=["leave-admin"])


def _read(t: LeaveType) -> LeaveTypeRead:
    return LeaveTypeRead(
        id=t.id,
        policy_id=t.policy_id,
        name=t.name,
        code=t.code,
        annual_quota_days=t.annual_quota_days,
        accrual=t.accrual,
        is_paid=t.is_paid,
        is_encashable=t.is_encashable,
        counts_toward_warning=t.counts_toward_warning,
        color_key=t.color_key,
        is_active=t.is_active,
    )


@router.get("/policies/{policy_id}/types", response_model=list[LeaveTypeRead])
async def list_types(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> list[LeaveTypeRead]:
    """All types on a policy, active and inactive."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    types = await LeaveTypeRepository(db, org_id=current_user.org_id).list_for_policy(policy.id)
    return [_read(t) for t in types]


@router.post(
    "/policies/{policy_id}/types",
    response_model=LeaveTypeRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_type(
    policy_id: uuid.UUID,
    body: LeaveTypeWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeRead:
    """Add a leave type to a policy."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    return _read(await type_admin.create_type(db, policy, current_user.id, body))


@router.put("/types/{type_id}", response_model=LeaveTypeRead)
async def update_type(
    type_id: uuid.UUID,
    body: LeaveTypeWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> LeaveTypeRead:
    """Edit a type. Quota changes apply to years not yet allocated."""
    leave_type = await LeaveTypeRepository(db, org_id=current_user.org_id).get_by_id(type_id)
    if leave_type is None:
        raise LeaveNotFoundError("Leave type not found.")
    await type_admin.update_type(db, leave_type, current_user.id, body)
    return _read(leave_type)
