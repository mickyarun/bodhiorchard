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

"""Adding and editing a policy's leave types, with a configuration trail.

Types are deactivated, never deleted. A quota change applies to leave
years not yet allocated; frozen years keep theirs unless HR recalculates.
How a type is given (upfront or monthly) can't change while this leave
year's allocation is booked.
"""

import uuid
from collections.abc import Mapping

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_config_event import LeaveConfigAction
from app.models.leave_policy import LeavePolicy
from app.models.leave_type import LeaveType
from app.repositories.leave_ledger import LeaveLedgerRepository
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.schemas.leave_policy import LeaveTypeWrite
from app.services.leave import config_audit
from app.services.leave.calendar_math import leave_year_bounds
from app.services.leave.errors import LeaveConflictError, LeaveForbiddenError
from app.services.leave.policies import today_for

# Only people who approve leave may set up leave that needs nobody's approval:
# otherwise a policy admin could book themselves leave no one ever decides.
AUTO_APPROVE_DENIED = (
    "Only people who approve leave can make a type approve itself. Ask HR or the org owner."
)


def _check_auto_approve(body: LeaveTypeWrite, may_approve: bool) -> None:
    if body.auto_approve and not may_approve:
        raise LeaveForbiddenError(AUTO_APPROVE_DENIED)


async def create_type(
    db: AsyncSession,
    policy: LeavePolicy,
    actor_id: uuid.UUID,
    body: LeaveTypeWrite,
    *,
    may_approve: bool,
) -> LeaveType:
    """Add a leave type to a policy."""
    _check_auto_approve(body, may_approve)
    repo = LeaveTypeRepository(db, org_id=policy.org_id)
    if await repo.code_taken(policy.id, body.code, exclude=None):
        raise LeaveConflictError(f"The code {body.code} is already used on this policy.")
    created = await repo.create(
        LeaveType(org_id=policy.org_id, policy_id=policy.id, **body.model_dump())
    )
    _record(
        db,
        created,
        actor_id,
        LeaveConfigAction.TYPE_CREATED,
        config_audit.diff({}, body.model_dump()),
    )
    return created


async def update_type(
    db: AsyncSession,
    leave_type: LeaveType,
    actor_id: uuid.UUID,
    body: LeaveTypeWrite,
    *,
    may_approve: bool,
) -> None:
    """Edit a type's name, code, quota, colour or active flag.

    A type that approves itself can only be edited by someone who approves
    leave: raising its allowance is as good as approving the extra days.
    """
    _check_auto_approve(body, may_approve)
    repo = LeaveTypeRepository(db, org_id=leave_type.org_id)
    if await repo.code_taken(leave_type.policy_id, body.code, exclude=leave_type.id):
        raise LeaveConflictError(f"The code {body.code} is already used on this policy.")
    if body.accrual != leave_type.accrual:
        await _check_accrual_change(db, leave_type)
    after = body.model_dump()
    changes = config_audit.diff(config_audit.snapshot(leave_type, after), after)
    if not changes:
        return
    for field, value in after.items():
        setattr(leave_type, field, value)
    await db.flush()
    _record(db, leave_type, actor_id, LeaveConfigAction.TYPE_UPDATED, changes)


async def _check_accrual_change(db: AsyncSession, leave_type: LeaveType) -> None:
    """Refuse to change how a type is given once this year's allocation is booked.

    Allocations are frozen per year, but accrual is read from the type, so a
    switch would re-time days already counted in a year in use: someone who
    took their upfront leave early would suddenly be overdrawn.
    """
    policy = await LeavePolicyRepository(db, org_id=leave_type.org_id).get_by_id(
        leave_type.policy_id
    )
    if policy is None:
        return
    year = leave_year_bounds(today_for(policy), policy.year_start_month)
    ledger = LeaveLedgerRepository(db, org_id=leave_type.org_id)
    if await ledger.allocated_since(leave_type.id, year.label):
        raise LeaveConflictError(
            "This type is already in use this leave year, so how it's given can't "
            "change now. Add a new type for the new rule, or change it next year."
        )


def _record(
    db: AsyncSession,
    leave_type: LeaveType,
    actor_id: uuid.UUID,
    action: LeaveConfigAction,
    changes: Mapping[str, object],
) -> None:
    # Name the type in every event so the policy's history reads on its own.
    config_audit.record(
        db,
        org_id=leave_type.org_id,
        actor_id=actor_id,
        action=action,
        policy_id=leave_type.policy_id,
        changes={"type": leave_type.code, **changes},
    )
