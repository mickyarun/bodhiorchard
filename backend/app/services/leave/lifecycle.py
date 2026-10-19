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

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.leave_request import ApprovalMode, LeaveRequest, LeaveStatus
from app.repositories.leave_request import LeaveRequestRepository
from app.schemas.leave import LeaveRequestCreate
from app.services.leave.approvers import approvers_for, route_for
from app.services.leave.evaluation import evaluate
from app.services.leave.evaluation_steps import Evaluation, apply_balance
from app.services.leave.policies import policy_for_request, resolve_member_policy


def conflict(detail: str) -> HTTPException:
    """A 409 with a reason the requester or approver can act on."""
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def submit(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, body: LeaveRequestCreate
) -> tuple[LeaveRequest, Evaluation]:
    """Create a request after re-checking every rule under the member's lock."""
    repo = LeaveRequestRepository(db, org_id=org_id)
    await repo.lock_member(user_id)
    member = await resolve_member_policy(db, org_id, user_id)
    result = await evaluate(db, member=member, user_id=user_id, body=body, persist=True)
    if result.problems:
        raise conflict(result.problems[0].message)
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Request not found.")
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
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    if not approve and not (note or "").strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Add a note so they know why it was rejected.",
        )
    repo = LeaveRequestRepository(db, org_id=org_id)
    await repo.lock_member(request.user_id)
    # Re-read under the lock: the status loaded above may already be stale.
    await db.refresh(request)
    if approve and request.status == LeaveStatus.PENDING:
        await _check_still_affordable(db, org_id, request)
    changed = await repo.transition(
        request.id,
        [LeaveStatus.PENDING],
        status=LeaveStatus.APPROVED if approve else LeaveStatus.REJECTED,
        decided_by=actor,
        decided_at=datetime.now(UTC),
        decision_note=(note or "").strip() or None,
    )
    if not changed:
        raise conflict("This request was already decided or cancelled.")
    await db.refresh(request)
    return request


async def _check_still_affordable(
    db: AsyncSession, org_id: uuid.UUID, request: LeaveRequest
) -> None:
    """Refuse to approve if the balance went negative since it was requested.

    Pending days already count against the balance, so this only trips when
    HR cut the balance or quota after the request was made. Only the balance
    is re-checked: date rules like the backdating limit applied when it was
    sent, and a request waiting in the queue mustn't dodge this by aging.
    """
    if request.leave_type_id is None:
        return
    member = await policy_for_request(db, org_id, request)
    result = Evaluation(start=request.start_date, end=request.end_date, days=request.days)
    await apply_balance(db, member, request.user_id, request.leave_type_id, result, persist=True)
    if result.balance_before is not None and result.balance_before < 0:
        raise conflict(
            f"Not enough balance: approving needs {request.days} days and only "
            f"{result.balance_before + request.days} are left. Reject, or ask HR to adjust it."
        )
