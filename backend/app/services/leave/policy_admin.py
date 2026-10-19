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

"""Creating, changing and assigning leave policies (HR / leave:configure).

Every change is checked here and recorded in the configuration trail in
the same transaction, so the route handlers only load, call and reply.
"""

import uuid
from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_config_event import LeaveConfigAction
from app.models.leave_policy import LeavePolicy
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_policy_members import LeavePolicyMemberRepository
from app.schemas.leave_policy import PolicyWrite
from app.services.leave import config_audit
from app.services.leave.errors import LeaveConflictError, LeaveForbiddenError
from app.services.leave.holidays import recount_requests
from app.services.leave.policies import today_for


async def create_policy(
    db: AsyncSession, org_id: uuid.UUID, actor_id: uuid.UUID, body: PolicyWrite
) -> LeavePolicy:
    """Add a policy, e.g. one per country."""
    repo = LeavePolicyRepository(db, org_id=org_id)
    if await repo.name_taken(body.name, exclude=None):
        raise LeaveConflictError(f"A policy called {body.name} already exists.")
    policy = await repo.create(LeavePolicy(org_id=org_id, **body.model_dump()))
    _record(
        db,
        policy,
        actor_id,
        LeaveConfigAction.POLICY_CREATED,
        config_audit.diff({}, body.model_dump()),
    )
    return policy


async def update_policy(
    db: AsyncSession, policy: LeavePolicy, actor_id: uuid.UUID, body: PolicyWrite
) -> None:
    """Change a policy. The leave-year start is fixed once requests exist.

    Changing working days or the timezone re-prices open requests, since
    their stored day counts depend on them.
    """
    repo = LeavePolicyRepository(db, org_id=policy.org_id)
    if await repo.name_taken(body.name, exclude=policy.id):
        raise LeaveConflictError(f"A policy called {body.name} already exists.")
    if body.year_start_month != policy.year_start_month and await repo.has_requests(policy.id):
        raise LeaveConflictError(
            "The leave year can't move once requests exist: every balance would shift."
        )
    after = body.model_dump()
    changes = config_audit.diff(config_audit.snapshot(policy, after), after)
    if not changes:
        return
    for field, value in after.items():
        setattr(policy, field, value)
    await db.flush()
    _record(db, policy, actor_id, LeaveConfigAction.POLICY_UPDATED, changes)
    if {"working_days", "timezone"} & changes.keys():
        await recount_requests(db, policy, today_for(policy))


async def make_default(db: AsyncSession, policy: LeavePolicy, actor_id: uuid.UUID) -> None:
    """Make this the policy for everyone without one of their own."""
    if policy.is_default:
        return
    await LeavePolicyRepository(db, org_id=policy.org_id).clear_default()
    policy.is_default = True
    await db.flush()
    _record(
        db, policy, actor_id, LeaveConfigAction.POLICY_MADE_DEFAULT, {"is_default": [False, True]}
    )


async def delete_policy(db: AsyncSession, policy: LeavePolicy, actor_id: uuid.UUID) -> None:
    """Delete an unused, non-default policy (its trail keeps the name)."""
    repo = LeavePolicyRepository(db, org_id=policy.org_id)
    if policy.is_default:
        raise LeaveConflictError("Make another policy the default before deleting this one.")
    if await repo.in_use(policy.id):
        raise LeaveConflictError(
            "This policy has employees, leave types or requests, so it stays."
        )
    _record(db, policy, actor_id, LeaveConfigAction.POLICY_DELETED, {"name": [policy.name, None]})
    await db.flush()
    await repo.delete(policy)


@dataclass(frozen=True)
class AssignResult:
    """How many moved, and how many of them still have requests pending from
    their old policy (decided on that policy's rules and balances)."""

    assigned: int
    pending_elsewhere: int


async def assign_employees(
    db: AsyncSession,
    policy: LeavePolicy,
    actor_id: uuid.UUID,
    user_ids: list[uuid.UUID],
    *,
    actor_is_owner: bool,
) -> AssignResult:
    """Move employees onto this policy from today; their old balances stay.

    Nobody but the owner moves themself: a policy with bigger quotas would
    otherwise be a way round "no adjusting your own balance". Quota edits
    and default changes that touch the editor's own leave are traced in
    the configuration trail, and their requests still need approval.
    """
    if actor_id in user_ids and not actor_is_owner:
        raise LeaveForbiddenError("Ask another admin to change your own leave policy.")
    members = LeavePolicyMemberRepository(db, org_id=policy.org_id)
    assigned = await members.assign_employees(policy, user_ids, today_for(policy))
    # Pending requests keep the policy they were made under (approval prices
    # them there), so HR is told about them rather than having them re-priced.
    pending_elsewhere = await members.count_pending_elsewhere(policy, user_ids)
    if assigned:
        _record(
            db,
            policy,
            actor_id,
            LeaveConfigAction.EMPLOYEES_ASSIGNED,
            {
                "user_ids": sorted(str(u) for u in user_ids),
                "assigned": assigned,
                "pending_elsewhere": pending_elsewhere,
            },
        )
    return AssignResult(assigned=assigned, pending_elsewhere=pending_elsewhere)


def _record(
    db: AsyncSession,
    policy: LeavePolicy,
    actor_id: uuid.UUID,
    action: LeaveConfigAction,
    changes: Mapping[str, object],
) -> None:
    config_audit.record(
        db,
        org_id=policy.org_id,
        actor_id=actor_id,
        action=action,
        policy_id=policy.id,
        changes=changes,
    )
