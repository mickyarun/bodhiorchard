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
"""Changing leave that's already approved (the person's managers, HR or the owner).

Until its last day is over, approved leave can have its approval withdrawn
here, or be moved or shortened (:mod:`app.services.leave.reschedule`).
Leave already under way keeps the days taken: only the rest moves or goes,
as when the requester cancels part of it. Every change runs under the
member's lock, like submit and decide; the caller tells the requester.
"""

import uuid
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.services.leave.approvers import approvers_for, route_for
from app.services.leave.cancellation import days_between
from app.services.leave.errors import LeaveConflictError, LeaveForbiddenError, LeaveInvalidError
from app.services.leave.lifecycle import load_request
from app.services.leave.loss_of_pay import rebalance
from app.services.leave.policies import MemberPolicy, policy_for_request, today_for

ZERO = Decimal("0")
CHANGED_MEANWHILE = "This request changed in the meantime. Refresh and try again."


async def changeable(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    request_id: uuid.UUID,
) -> tuple[LeaveRequest, MemberPolicy, date]:
    """The request, its policy and the policy's today, once the actor may change it."""
    request = await load_request(db, org_id, request_id)
    approvers = await approvers_for(db, org_id, request.user_id)
    if route_for(actor, perms, request.user_id, approvers) is None:
        raise LeaveForbiddenError(
            "You can't change your own leave this way."
            if actor == request.user_id
            else "Only this person's managers, HR or the owner can change their leave."
        )
    member = await policy_for_request(db, org_id, request)
    # Policy before member, as submit does: no deadlock.
    await LeavePolicyRepository(db, org_id=org_id).lock(member.policy.id, shared=True)
    await LeaveRequestRepository(db, org_id=org_id).lock_member(request.user_id)
    await db.refresh(request)
    today = today_for(member.policy)
    if request.status != LeaveStatus.APPROVED or request.end_date < today:
        raise LeaveConflictError("Only approved leave that isn't over yet can be changed.")
    return request, member, today


def decided_fields(actor: uuid.UUID, note: str | None) -> dict[str, Any]:
    """Who changed it, when, and their note (shown to the requester)."""
    return {
        "decided_by": actor,
        "decided_at": datetime.now(UTC),
        "decision_note": (note or "").strip() or None,
    }


async def withdraw(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    request_id: uuid.UUID,
    note: str | None,
) -> LeaveRequest:
    """Take back an approval: rejected outright, or ended today if under way."""
    if not (note or "").strip():
        raise LeaveInvalidError("Add a note so they know why.")
    request, member, today = await changeable(db, org_id, actor, perms, request_id)
    taken = ZERO
    if request.start_date < today:
        yesterday = today - timedelta(days=1)
        taken = await days_between(db, member.policy, request, request.start_date, yesterday)
    repo = LeaveRequestRepository(db, org_id=org_id)
    if taken == ZERO:
        changed = await repo.transition(
            request.id,
            [LeaveStatus.APPROVED],
            status=LeaveStatus.REJECTED,
            **decided_fields(actor, note),
        )
    else:
        changed = await repo.transition(
            request.id,
            [LeaveStatus.APPROVED],
            end_date=today - timedelta(days=1),
            days=taken,
            lop_days=max(ZERO, request.lop_days - (request.days - taken)),
            **decided_fields(actor, note),
        )
    if not changed:
        raise LeaveConflictError(CHANGED_MEANWHILE)
    await db.refresh(request)
    if request.leave_type_id is not None:
        await rebalance(db, member, request.user_id, request.leave_type_id, request.start_date)
    return request
