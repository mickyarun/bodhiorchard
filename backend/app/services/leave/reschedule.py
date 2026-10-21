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
"""Moving or shortening approved leave (managers, HR or the owner).

The new dates are checked like a new request. Leave not started yet is set
aside inside the transaction while they're checked, so it doesn't count
against itself; a problem rolls everything back. Leave under way keeps
its start and the days taken: only its end moves, and added days are
checked with the rest still counted.
"""

import uuid
from collections.abc import Sequence
from datetime import date, timedelta
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.leave_request import HalfDay, LeaveKind, LeaveRequest, LeaveStatus
from app.repositories.leave_request import LeaveRequestRepository
from app.schemas.leave import LeaveProblem, LeaveRequestCreate
from app.services.leave.calendar_math import same_leave_year
from app.services.leave.cancellation import days_between
from app.services.leave.changes import CHANGED_MEANWHILE, changeable, decided_fields
from app.services.leave.errors import LeaveConflictError, LeaveInvalidError
from app.services.leave.evaluation import evaluate
from app.services.leave.loss_of_pay import give_back, reprice
from app.services.leave.policies import MemberPolicy

# The editor is an approver, so "nobody can approve this" doesn't apply.
_IGNORED_PROBLEMS = {"no_approver"}


async def reschedule(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor: uuid.UUID,
    perms: PermissionSet,
    request_id: uuid.UUID,
    start: date,
    end: date,
    half_day: HalfDay,
    note: str | None,
) -> LeaveRequest:
    """Move or shorten approved leave; it stays approved under the new dates."""
    request, member, today = await changeable(db, org_id, actor, perms, request_id)
    if request.kind == LeaveKind.OPTIONAL_HOLIDAY:
        raise LeaveInvalidError("An optional holiday can't move. Withdraw it instead.")
    if (start, end, half_day) == (request.start_date, request.end_date, request.half_day):
        raise LeaveInvalidError("Those are already its dates.")
    old_start = request.start_date
    if request.start_date < today:
        days = await _reschedule_under_way(db, member, request, today, start, end, half_day)
    else:
        days = await _reschedule_ahead(db, member, request, today, start, end, half_day)
    changed = await LeaveRequestRepository(db, org_id=org_id).transition(
        request.id,
        [LeaveStatus.APPROVED, LeaveStatus.CANCELLED],
        status=LeaveStatus.APPROVED,
        start_date=start,
        end_date=end,
        half_day=half_day,
        days=days,
        **decided_fields(actor, note),
    )
    if not changed:
        raise LeaveConflictError(CHANGED_MEANWHILE)
    await db.refresh(request)
    # Re-split paid and unpaid days for the new length; freed balance goes
    # to their other leave that had loss of pay, in the year the days left
    # too when it moved across years.
    await reprice(db, member, request)
    if request.leave_type_id is not None:
        for day in {old_start, request.start_date}:
            await give_back(db, member, request.user_id, request.leave_type_id, day)
    return request


async def _reschedule_ahead(
    db: AsyncSession,
    member: MemberPolicy,
    request: LeaveRequest,
    today: date,
    start: date,
    end: date,
    half_day: HalfDay,
) -> Decimal:
    """Not started: check the new dates as if newly asked, with this one set aside."""
    if start < today:
        raise LeaveInvalidError("Pick dates from today on.")
    body = _body(request, start, end, half_day)
    # Set aside inside this transaction so the checks don't count it twice;
    # any problem rolls it back.
    repo = LeaveRequestRepository(db, org_id=request.org_id)
    if not await repo.transition(request.id, [LeaveStatus.APPROVED], status=LeaveStatus.CANCELLED):
        raise LeaveConflictError(CHANGED_MEANWHILE)
    await db.flush()
    result = await evaluate(db, member=member, user_id=request.user_id, body=body, persist=True)
    await _refuse_problems(db, result.problems)
    return result.days


async def _reschedule_under_way(
    db: AsyncSession,
    member: MemberPolicy,
    request: LeaveRequest,
    today: date,
    start: date,
    end: date,
    half_day: HalfDay,
) -> Decimal:
    """Started: only the end moves. Days taken stay; added days are checked."""
    if start != request.start_date or half_day != request.half_day:
        raise LeaveInvalidError("This leave has started, so only its end date can change.")
    if end < today:
        raise LeaveInvalidError("Pick today or later. To end it before today, withdraw the rest.")
    # The whole leave keeps the rules a new request has: one leave year.
    _body(request, start, end, half_day)
    if not same_leave_year(start, end, member.policy.year_start_month):
        raise LeaveInvalidError("Leave can't run into the next leave year. Book the rest anew.")
    if end <= request.end_date:
        days = await days_between(db, member.policy, request, start, end)
        if days == 0:
            raise LeaveInvalidError(
                "Those dates are all weekends or holidays. Withdraw it instead."
            )
        return days
    # Longer: the added days are checked like a new request, with the days
    # already booked still counted.
    added = _body(request, request.end_date + timedelta(days=1), end, HalfDay.NONE)
    result = await evaluate(db, member=member, user_id=request.user_id, body=added, persist=True)
    await _refuse_problems(db, result.problems)
    return request.days + result.days


def _body(request: LeaveRequest, start: date, end: date, half_day: HalfDay) -> LeaveRequestCreate:
    try:
        return LeaveRequestCreate(
            kind=request.kind,
            leave_type_id=request.leave_type_id,
            start_date=start,
            end_date=end,
            half_day=half_day,
        )
    except ValidationError as exc:
        message = str(exc.errors()[0].get("msg", "Those dates don't work."))
        raise LeaveInvalidError(message.removeprefix("Value error, ")) from exc


async def _refuse_problems(db: AsyncSession, problems: Sequence[LeaveProblem]) -> None:
    """Undo everything this change did and refuse with the first real problem."""
    real = [p for p in problems if p.code not in _IGNORED_PROBLEMS]
    if real:
        await db.rollback()
        raise LeaveConflictError(real[0].message)
