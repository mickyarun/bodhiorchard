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

"""The team calendar: who's out, with type and reason only where allowed."""

import uuid
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.repositories.user import UserRepository
from app.schemas.leave import LeaveTypeBrief, PersonRef
from app.schemas.leave_views import CalendarEntry, CalendarRead
from app.services.leave.permissions import APPROVE
from app.services.leave.policies import resolve_member_policy
from app.services.leave.summary import holiday_schema
from app.services.leave.type_privacy import sees_restricted, shown


async def calendar_view(
    db: AsyncSession,
    org_id: uuid.UUID,
    viewer: uuid.UUID,
    perms: PermissionSet,
    start: date,
    end: date,
) -> CalendarRead:
    """Approved requests in a range (plus the viewer's pending ones).

    Leave type and reason are included only for the requester, their
    managers and HR. Everyone else sees "on leave" — the response carries
    no field a client could use to infer sick leave. A gender-limited type
    (period leave) is named to managers only if they see personal details.
    """
    requests = await LeaveRequestRepository(db, org_id=org_id).calendar(start, end, viewer)
    edges = await EmployeeReportingManagerRepository(db, org_id=org_id).reporting_edges()
    reports = {who for who, boss in edges if boss == viewer}
    hr = perms.has(APPROVE)
    sees = sees_restricted(perms)
    names = await UserRepository(db).get_names_by_ids({r.user_id for r in requests})
    types = await LeaveTypeRepository(db, org_id=org_id).by_ids(
        {r.leave_type_id for r in requests if r.leave_type_id}
    )
    policies = await LeavePolicyRepository(db, org_id=org_id).by_ids(
        {r.policy_id for r in requests}
    )
    entries = []
    for r in requests:
        private = hr or r.user_id == viewer or r.user_id in reports
        leave_type = types.get(r.leave_type_id) if private and r.leave_type_id else None
        if not shown(leave_type, sees_all=sees or r.user_id == viewer):
            leave_type = None
        entries.append(
            CalendarEntry(
                request_id=r.id,
                user=PersonRef(user_id=r.user_id, name=names.get(r.user_id, "Someone")),
                kind=r.kind,
                start_date=r.start_date,
                end_date=r.end_date,
                half_day=r.half_day,
                status=r.status,
                is_own=r.user_id == viewer,
                leave_type=LeaveTypeBrief(
                    id=leave_type.id,
                    name=leave_type.name,
                    code=leave_type.code,
                    color_key=leave_type.color_key,
                )
                if leave_type
                else None,
                reason=r.reason if private else None,
                working_days=list(policies[r.policy_id].working_days),
            )
        )
    member = await resolve_member_policy(db, org_id, viewer)
    holidays = await PolicyHolidayRepository(db, org_id=org_id).list_between(
        member.policy.id, start, end
    )
    return CalendarRead(entries=entries, holidays=[holiday_schema(h) for h in holidays])
