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

"""Submit, approve and reject requests (cancelling lives in
:mod:`app.services.leave.cancellation`).

Every change takes the requester's row lock first and re-checks the
rules, and status changes are conditional updates: if two managers click
at once, the second gets "already decided" instead of a double decision.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.leave_request import ApprovalMode, LeaveRequest, LeaveStatus
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.user import UserRepository
from app.schemas.leave import LeaveRequestCreate
from app.services.fixed_window import seconds_until_allowed
from app.services.leave.approvers import approvers_for, route_for
from app.services.leave.errors import (
    LeaveConflictError,
    LeaveForbiddenError,
    LeaveInvalidError,
    LeaveNotFoundError,
    LeaveRateLimitedError,
)
from app.services.leave.evaluation import evaluate
from app.services.leave.evaluation_steps import Evaluation
from app.services.leave.loss_of_pay import rebalance, reprice
from app.services.leave.messages import already_decided_message
from app.services.leave.policies import policy_for_request, resolve_member_policy

# Far above anyone's real use; low enough that approvers can't be spammed.
SUBMITS_PER_WINDOW = 20
SUBMIT_WINDOW_SECONDS = 3600


async def submit(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, body: LeaveRequestCreate
) -> tuple[LeaveRequest, Evaluation]:
    """Create a request after re-checking every rule under the member's lock.

    Throttled per member: each request notifies approvers (on Slack too),
    so a submit/cancel loop mustn't be able to flood them. Every attempt
    counts, including refused ones.
    """
    wait = await seconds_until_allowed(
        f"leave_submit:{org_id}:{user_id}",
        limit=SUBMITS_PER_WINDOW,
        window_seconds=SUBMIT_WINDOW_SECONDS,
    )
    if wait:
        raise LeaveRateLimitedError(
            "You've sent a lot of requests in the last hour. Try again a little later.",
            retry_after_seconds=wait,
        )
    repo = LeaveRequestRepository(db, org_id=org_id)
    # Policy before member, like a calendar change: no deadlock, and the
    # days are counted against holidays that can't change underneath.
    policy_id = (await resolve_member_policy(db, org_id, user_id)).policy.id
    await LeavePolicyRepository(db, org_id=org_id).lock(policy_id, shared=True)
    await repo.lock_member(user_id)
    member = await resolve_member_policy(db, org_id, user_id)
    result = await evaluate(db, member=member, user_id=user_id, body=body, persist=True)
    if result.problems:
        raise LeaveConflictError(result.problems[0].message)
    auto = result.auto_approved
    request = await repo.create(
        LeaveRequest(
            org_id=org_id,
            user_id=user_id,
            policy_id=member.policy.id,
            kind=body.kind,
            leave_type_id=body.leave_type_id,
            holiday_id=result.holiday.id if result.holiday else None,
            start_date=result.start,
            end_date=result.end,
            half_day=body.half_day,
            days=result.days,
            lop_days=result.lop_days,
            reason=(body.reason or "").strip() or None,
            status=LeaveStatus.APPROVED if auto else LeaveStatus.PENDING,
            approval_mode=ApprovalMode.AUTO_POLICY if auto else ApprovalMode.MANUAL,
            decided_at=datetime.now(UTC) if auto else None,
        )
    )
    return request, result


async def load_request(db: AsyncSession, org_id: uuid.UUID, request_id: uuid.UUID) -> LeaveRequest:
    """A request in this org, or 404."""
    request = await LeaveRequestRepository(db, org_id=org_id).get_by_id(request_id)
    if request is None:
        raise LeaveNotFoundError("Request not found.")
    return request


async def decide(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    request_id: uuid.UUID,
    approve: bool,
    note: str | None,
) -> LeaveRequest:
    """Approve or reject a pending request."""
    request = await load_request(db, org_id, request_id)
    approvers = await approvers_for(db, org_id, request.user_id)
    if route_for(actor, perms, request.user_id, approvers) is None:
        detail = (
            "You can't decide your own request."
            if actor == request.user_id
            else "Only this person's managers or HR can decide this request."
        )
        raise LeaveForbiddenError(detail)
    if not approve and not (note or "").strip():
        raise LeaveInvalidError("Add a note so they know why it was rejected.")
    repo = LeaveRequestRepository(db, org_id=org_id)
    await repo.lock_member(request.user_id)
    # Re-read under the lock: the status loaded above may already be stale.
    await db.refresh(request)
    if approve and request.status == LeaveStatus.PENDING:
        # The balance may have moved since it was sent (an adjustment, another
        # approval): price it again so loss of pay is right when it's approved.
        await reprice(db, await policy_for_request(db, org_id, request), request)
        await _refuse_if_over(db, org_id, request)
    changed = await repo.transition(
        request.id,
        [LeaveStatus.PENDING],
        status=LeaveStatus.APPROVED if approve else LeaveStatus.REJECTED,
        decided_by=actor,
        decided_at=datetime.now(UTC),
        decision_note=(note or "").strip() or None,
    )
    if not changed:
        raise LeaveConflictError(await already_decided(db, org_id, request))
    await db.refresh(request)
    if not approve and request.leave_type_id is not None:
        # The rejected request's paid days are free again.
        member = await policy_for_request(db, org_id, request)
        await rebalance(db, member, request.user_id, request.leave_type_id, request.start_date)
    return request


async def _refuse_if_over(db: AsyncSession, org_id: uuid.UUID, request: LeaveRequest) -> None:
    """A type that stops at its balance isn't approved into loss of pay.

    Its balance can drop after the request was sent (HR took days off), so
    the approver is told to send it back rather than approve unpaid days.
    """
    if request.lop_days <= 0 or request.leave_type_id is None:
        return
    leave_type = await LeaveTypeRepository(db, org_id=org_id).get_by_id(request.leave_type_id)
    if leave_type is not None and leave_type.stops_at_balance:
        raise LeaveConflictError(
            f"Their {leave_type.name} balance went down after they asked, and this request "
            "is now past it. Reject it so they can request the rest as another type."
        )


async def already_decided(db: AsyncSession, org_id: uuid.UUID, request: LeaveRequest) -> str:
    """What a second approver is told: who decided first, or that it was cancelled."""
    await db.refresh(request)
    decider = None
    if request.decided_by is not None:
        names = await UserRepository(db, org_id=org_id).get_names_by_ids({request.decided_by})
        decider = names.get(request.decided_by)
    return already_decided_message(request, decider)
