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

"""Every request overlapping a range: the register report and a member's history.

The policy filter here means the policy a request was priced on, not the
member's current one, so a past request stays under the rules it followed.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveKind, LeaveStatus
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_report import LeaveReportRepository
from app.repositories.leave_request_filter import RequestFilter
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.user import UserRepository
from app.schemas.leave_report_filters import PeopleFilters, RegisterFilters
from app.schemas.leave_reports import RegisterReport, RegisterRow
from app.services.leave.calendar_math import leave_year_bounds, leave_year_by_label
from app.services.leave.policies import resolve_member_policy, today_for
from app.services.leave.report_scope import ReportScope
from app.services.leave.reports.population import people, scoped_ids
from app.services.leave.type_privacy import shown

REGISTER_CAP = 5_000
UNKNOWN_NAME = "Unknown"


async def register_report(
    db: AsyncSession, org_id: uuid.UUID, scope: ReportScope, f: RegisterFilters
) -> RegisterReport:
    """Requests in the range within ``scope``, by start date; at most REGISTER_CAP.

    Gender-limited types show as plain leave unless the scope may see them;
    filtering on one then finds nothing (it would list who took it).
    """
    type_repo = LeaveTypeRepository(db, org_id=org_id)
    if f.leave_type_id and not scope.sees_restricted:
        asked = await type_repo.get_by_id(f.leave_type_id)
        if asked is not None and not shown(asked, sees_all=False):
            return RegisterReport(rows=[], truncated=False)
    ids = await scoped_ids(db, org_id, scope, f)
    if f.department or f.office_id:
        place = PeopleFilters(department=f.department, office_id=f.office_id)
        ids = frozenset(p.user_id for p in await people(db, org_id, ids, place))
    filters = RequestFilter(
        kind=f.kind,
        leave_type_id=f.leave_type_id,
        statuses=(f.status,) if f.status else None,
        policy_id=f.policy_id,
    )
    requests = await LeaveReportRepository(db, org_id=org_id).overlapping(
        ids, f.start, f.end, filters, limit=REGISTER_CAP + 1
    )
    truncated = len(requests) > REGISTER_CAP
    requests = requests[:REGISTER_CAP]
    users = {r.user_id for r in requests}
    profiles = await EmployeeProfileRepository(db, org_id=org_id).by_users(users)
    names = await UserRepository(db).get_names_by_ids(
        users | {r.decided_by for r in requests if r.decided_by}
    )
    types = await type_repo.by_ids({r.leave_type_id for r in requests if r.leave_type_id})
    rows = []
    for r in requests:
        profile = profiles.get(r.user_id)
        leave_type = types.get(r.leave_type_id) if r.leave_type_id else None
        if not shown(leave_type, sees_all=scope.sees_restricted):
            leave_type = None
        rows.append(
            RegisterRow(
                request_id=r.id,
                user_id=r.user_id,
                name=names.get(r.user_id, UNKNOWN_NAME),
                employee_code=profile.employee_code if profile else None,
                department=profile.department if profile else None,
                kind=r.kind,
                leave_type=leave_type.name if leave_type else None,
                start_date=r.start_date,
                end_date=r.end_date,
                half_day=r.half_day,
                days=r.days,
                lop_days=r.lop_days,
                status=r.status,
                approval_mode=r.approval_mode,
                requested_at=r.created_at,
                decided_by=names.get(r.decided_by) if r.decided_by else None,
                decided_at=r.decided_at,
            )
        )
    return RegisterReport(rows=rows, truncated=truncated)


async def member_history(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    year: int | None,
    *,
    sees_restricted: bool,
    kind: LeaveKind | None = None,
    status: LeaveStatus | None = None,
) -> RegisterReport:
    """One member's requests in a leave year of their current policy (now by default)."""
    policy = (await resolve_member_policy(db, org_id, user_id)).policy
    bounds = (
        leave_year_by_label(year, policy.year_start_month)
        if year
        else leave_year_bounds(today_for(policy), policy.year_start_month)
    )
    filters = RegisterFilters(start=bounds.start, end=bounds.end, kind=kind, status=status)
    scope = ReportScope(frozenset({user_id}), sees_restricted)
    return await register_report(db, org_id, scope, filters)
