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

"""Build request responses, hiding leave type and reason where required.

Sick leave is private: only the requester, their managers and HR see a
request's type and reason. Callers pass ``private_ok`` to say whether the
viewer is one of them.
"""

import uuid
from collections.abc import Callable, Sequence
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveRequest, LeaveStatus
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.repositories.user import UserRepository
from app.schemas.leave import LeaveRequestRead, LeaveTypeBrief, PersonRef


def can_cancel(request: LeaveRequest, viewer: uuid.UUID, today: date) -> bool:
    """The requester may cancel pending requests and approved ones not yet over."""
    if request.user_id != viewer:
        return False
    if request.status == LeaveStatus.PENDING:
        return True
    return request.status == LeaveStatus.APPROVED and request.end_date >= today


async def request_reads(
    db: AsyncSession,
    org_id: uuid.UUID,
    requests: Sequence[LeaveRequest],
    *,
    viewer: uuid.UUID,
    today: date,
    private_ok: Callable[[LeaveRequest], bool],
) -> list[LeaveRequestRead]:
    """Responses for ``requests`` with names, types and holidays resolved."""
    people = {r.user_id for r in requests} | {r.decided_by for r in requests if r.decided_by}
    names = await UserRepository(db).get_names_by_ids(people)
    types = await LeaveTypeRepository(db, org_id=org_id).by_ids(
        {r.leave_type_id for r in requests if r.leave_type_id}
    )
    holidays = await PolicyHolidayRepository(db, org_id=org_id).by_ids(
        {r.holiday_id for r in requests if r.holiday_id}
    )
    out = []
    for r in requests:
        private = private_ok(r)
        leave_type = types.get(r.leave_type_id) if r.leave_type_id and private else None
        holiday = holidays.get(r.holiday_id) if r.holiday_id else None
        out.append(
            LeaveRequestRead(
                id=r.id,
                user=PersonRef(user_id=r.user_id, name=names.get(r.user_id, "Unknown")),
                kind=r.kind,
                leave_type=LeaveTypeBrief(
                    id=leave_type.id,
                    name=leave_type.name,
                    code=leave_type.code,
                    color_key=leave_type.color_key,
                )
                if leave_type
                else None,
                holiday_name=holiday.name if holiday else None,
                start_date=r.start_date,
                end_date=r.end_date,
                half_day=r.half_day,
                days=r.days,
                reason=r.reason if private else None,
                status=r.status,
                approval_mode=r.approval_mode,
                decided_by=PersonRef(user_id=r.decided_by, name=names.get(r.decided_by, "Unknown"))
                if r.decided_by
                else None,
                decided_at=r.decided_at,
                decision_note=r.decision_note if private else None,
                created_at=r.created_at,
                can_cancel=can_cancel(r, viewer, today),
            )
        )
    return out
