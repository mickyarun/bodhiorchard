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

"""Leave policies (one per country or location) and who follows each."""

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._leave_admin import CONFIGURE, load_policy, policy_read
from app.core.deps import PermissionSet, get_db, get_permission_set, require_permissions
from app.models.user import User
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_policy_members import LeavePolicyMemberRepository
from app.schemas.leave import PersonRef
from app.schemas.leave_config import ConfigEventRead
from app.schemas.leave_policy import PolicyAssign, PolicyRead, PolicyWrite
from app.services.leave import policy_admin
from app.services.leave.config_history import config_history
from app.services.leave.policies import ensure_default_policy

router = APIRouter(tags=["leave-admin"])


@router.get("/policies", response_model=list[PolicyRead])
async def list_policies(
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> list[PolicyRead]:
    """Every policy, default first. Creates the default on first visit."""
    await ensure_default_policy(db, current_user.org_id)
    policies = await LeavePolicyRepository(db, org_id=current_user.org_id).list_ordered()
    return [await policy_read(db, p) for p in policies]


@router.post("/policies", response_model=PolicyRead, status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: PolicyWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> PolicyRead:
    """Add a policy, e.g. one per country."""
    policy = await policy_admin.create_policy(db, current_user.org_id, current_user.id, body)
    return await policy_read(db, policy)


@router.put("/policies/{policy_id}", response_model=PolicyRead)
async def update_policy(
    policy_id: uuid.UUID,
    body: PolicyWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> PolicyRead:
    """Change a policy. The leave-year start is fixed once requests exist."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    await policy_admin.update_policy(db, policy, current_user.id, body)
    return await policy_read(db, policy)


@router.post("/policies/{policy_id}/default", response_model=PolicyRead)
async def make_default(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> PolicyRead:
    """Make this the policy for everyone without one of their own."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    await policy_admin.make_default(db, policy, current_user.id)
    return await policy_read(db, policy)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an unused, non-default policy."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    await policy_admin.delete_policy(db, policy, current_user.id)


@router.get("/policies/{policy_id}/employees", response_model=list[PersonRef])
async def policy_employees(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> list[PersonRef]:
    """Employees following the policy (the default includes the unassigned)."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    rows = await LeavePolicyMemberRepository(db, org_id=current_user.org_id).list_employees(policy)
    return [PersonRef(user_id=uid, name=name) for uid, name in rows]


@router.post("/policies/{policy_id}/assign")
async def assign_policy(
    policy_id: uuid.UUID,
    body: PolicyAssign,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Move employees onto this policy from today (never yourself, unless owner)."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    result = await policy_admin.assign_employees(
        db, policy, current_user.id, body.user_ids, actor_is_owner=perms.is_owner
    )
    return {"assigned": result.assigned, "pending_elsewhere": result.pending_elsewhere}


@router.get("/policies/{policy_id}/history", response_model=list[ConfigEventRead])
async def policy_history(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> list[ConfigEventRead]:
    """Who changed this policy and its leave types, newest first."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    return await config_history(db, policy)
