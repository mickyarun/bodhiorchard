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

"""Cancelling a request.

Pending and not-yet-started approved requests are cancelled outright.
Approved leave already under way keeps the working days already taken
and gives back the rest. Like every change, it runs under the requester's
row lock with a conditional status update.
"""

import uuid
from datetime import timedelta

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveRequest, LeaveStatus
from app.repositories.leave_request import LeaveRequestRepository
from app.services.leave.calendar_math import count_days
from app.services.leave.lifecycle import conflict, load_request
from app.services.leave.policies import mandatory_holidays, policy_for_request, today_for


async def cancel(
    db: AsyncSession, org_id: uuid.UUID, actor: uuid.UUID, request_id: uuid.UUID
) -> LeaveRequest:
    """Cancel a request; leave already under way keeps the days already taken."""
    request = await load_request(db, org_id, request_id)
    if request.user_id != actor:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="You can only cancel your own requests."
        )
    repo = LeaveRequestRepository(db, org_id=org_id)
    await repo.lock_member(actor)
    # Re-read under the lock: a manager may have decided it meanwhile.
    await db.refresh(request)
    # Count taken days on the policy it was booked under.
    member = await policy_for_request(db, org_id, request)
    today = today_for(member.policy)
    if request.status == LeaveStatus.APPROVED and request.start_date < today <= request.end_date:
        # Under way: keep the days already taken, cancel the rest.
        yesterday = today - timedelta(days=1)
        holidays = await mandatory_holidays(db, member.policy, request.start_date, yesterday)
        taken = count_days(
            request.start_date,
            yesterday,
            request.half_day,
            working_days=member.policy.working_days,
            holidays=holidays,
        )
        if taken.days == 0:
            # Only non-working days have passed: nothing was taken yet.
            changed = await repo.transition(
                request.id, [LeaveStatus.APPROVED], status=LeaveStatus.CANCELLED
            )
        else:
            changed = await repo.transition(
                request.id, [LeaveStatus.APPROVED], end_date=yesterday, days=taken.days
            )
    elif request.status == LeaveStatus.PENDING:
        changed = await repo.transition(
            request.id, [LeaveStatus.PENDING], status=LeaveStatus.CANCELLED
        )
    elif request.status == LeaveStatus.APPROVED and request.start_date >= today:
        changed = await repo.transition(
            request.id, [LeaveStatus.APPROVED], status=LeaveStatus.CANCELLED
        )
    else:
        raise conflict("This request can't be cancelled any more.")
    if not changed:
        raise conflict("This request changed in the meantime. Refresh and try again.")
    await db.refresh(request)
    return request
