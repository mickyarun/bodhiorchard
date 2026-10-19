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

from app.api.v1._leave_admin import CONFIGURE, conflict, load_policy, policy_read
from app.core.deps import get_db, require_permissions
from app.models.leave_policy import LeavePolicy
from app.models.user import User
from app.repositories.leave_policy import LeavePolicyRepository
from app.schemas.leave import PersonRef
from app.schemas.leave_policy import PolicyAssign, PolicyRead, PolicyWrite
from app.services.leave.holidays import recount_requests
from app.services.leave.policies import ensure_default_policy, today_for

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
    repo = LeavePolicyRepository(db, org_id=current_user.org_id)
    if await repo.name_taken(body.name, exclude=None):
        raise conflict(f"A policy called {body.name} already exists.")
    policy = await repo.create(LeavePolicy(org_id=current_user.org_id, **body.model_dump()))
    return await policy_read(db, policy)


@router.put("/policies/{policy_id}", response_model=PolicyRead)
async def update_policy(
    policy_id: uuid.UUID,
    body: PolicyWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> PolicyRead:
    """Change a policy. The leave-year start is fixed once requests exist."""
    repo = LeavePolicyRepository(db, org_id=current_user.org_id)
    policy = await load_policy(db, current_user.org_id, policy_id)
    if await repo.name_taken(body.name, exclude=policy.id):
        raise conflict(f"A policy called {body.name} already exists.")
    if body.year_start_month != policy.year_start_month and await repo.has_requests(policy.id):
        raise conflict("The leave year can't move once requests exist: every balance would shift.")
    calendar_changed = (
        sorted(body.working_days) != sorted(policy.working_days)
        or body.timezone != policy.timezone
    )
    for field, value in body.model_dump().items():
        setattr(policy, field, value)
    await db.flush()
    if calendar_changed:
        # Stored day counts depend on working days; keep them honest.
        await recount_requests(db, policy, today_for(policy))
    return await policy_read(db, policy)


@router.post("/policies/{policy_id}/default", response_model=PolicyRead)
async def make_default(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> PolicyRead:
    """Make this the policy for everyone without one of their own."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    await LeavePolicyRepository(db, org_id=current_user.org_id).clear_default()
    policy.is_default = True
    await db.flush()
    return await policy_read(db, policy)


@router.delete("/policies/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an unused, non-default policy."""
    repo = LeavePolicyRepository(db, org_id=current_user.org_id)
    policy = await load_policy(db, current_user.org_id, policy_id)
    if policy.is_default:
        raise conflict("Make another policy the default before deleting this one.")
    if await repo.in_use(policy.id):
        raise conflict("This policy has employees, leave types or requests, so it stays.")
    await repo.delete(policy)


@router.get("/policies/{policy_id}/employees", response_model=list[PersonRef])
async def policy_employees(
    policy_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> list[PersonRef]:
    """Employees following the policy (the default includes the unassigned)."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    rows = await LeavePolicyRepository(db, org_id=current_user.org_id).list_employees(policy)
    return [PersonRef(user_id=uid, name=name) for uid, name in rows]


@router.post("/policies/{policy_id}/assign")
async def assign_policy(
    policy_id: uuid.UUID,
    body: PolicyAssign,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> dict[str, int]:
    """Move employees onto this policy from today; their old balances stay."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    assigned = await LeavePolicyRepository(db, org_id=current_user.org_id).assign_employees(
        policy, body.user_ids, today_for(policy)
    )
    return {"assigned": assigned}
