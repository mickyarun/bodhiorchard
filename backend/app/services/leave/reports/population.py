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

"""The people a report covers, with the columns every report shows.

Members with a profile, plus active members with none yet and anyone who
took leave without one (they follow the default policy), so a payroll export
never silently drops them. Those without a profile are left out only by a
filter they can't match: a department, an office, or a non-default policy.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_policy import LeavePolicy
from app.models.office_location import OfficeLocation
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_report import LeaveReportRepository
from app.repositories.office_location import OfficeLocationRepository
from app.repositories.user import UserRepository
from app.schemas.leave_report_filters import PeopleFilters
from app.schemas.leave_reports import PersonColumns
from app.services.leave.report_scope import ReportScope


@dataclass(frozen=True)
class Person:
    """A member as reports show them."""

    columns: PersonColumns
    profile: EmployeeProfile | None
    policy: LeavePolicy | None
    office: OfficeLocation | None = None

    @property
    def user_id(self) -> uuid.UUID:
        return self.columns.user_id


async def scoped_ids(
    db: AsyncSession, org_id: uuid.UUID, scope: ReportScope, filters: PeopleFilters
) -> frozenset[uuid.UUID] | None:
    """The scope narrowed by person and manager filters; never wider than ``scope``."""
    narrowed = scope.narrow(filters.user_id).user_ids
    if filters.manager_id is None:
        return narrowed
    edges = await EmployeeReportingManagerRepository(db, org_id=org_id).reporting_edges()
    team = frozenset(e for e, boss in edges if boss == filters.manager_id)
    return team if narrowed is None else narrowed & team


async def people(
    db: AsyncSession,
    org_id: uuid.UUID,
    ids: frozenset[uuid.UUID] | None,
    filters: PeopleFilters,
    *,
    requesters: Collection[uuid.UUID] = (),
) -> list[Person]:
    """Profiles matching ``filters`` within ``ids``, plus profile-less ``requesters``."""
    policy_repo = LeavePolicyRepository(db, org_id=org_id)
    default = await policy_repo.get_default()
    rows = await LeaveReportRepository(db, org_id=org_id).profiles(
        ids,
        department=filters.department,
        office_id=filters.office_id,
        policy_id=filters.policy_id,
        policy_is_default=default is not None and filters.policy_id == default.id,
    )
    profiles = [row.profile for row in rows]
    policies = await policy_repo.by_ids({p.leave_policy_id for p in profiles if p.leave_policy_id})
    offices = await OfficeLocationRepository(db, org_id=org_id).by_ids(
        {p.office_id for p in profiles if p.office_id}
    )
    managers = await EmployeeReportingManagerRepository(db, org_id=org_id).list_for_profiles(
        [p.id for p in profiles]
    )
    out: list[Person] = []
    for row in rows:
        p = row.profile
        policy = policies.get(p.leave_policy_id) if p.leave_policy_id else default
        office = offices.get(p.office_id) if p.office_id else None
        primary = next(iter(managers.get(p.id, [])), None)
        columns = PersonColumns(
            user_id=p.user_id,
            name=row.name,
            employee_code=p.employee_code,
            department=p.department,
            office=office.name if office else None,
            policy=policy.name if policy else None,
            manager=primary.name if primary else None,
            status=p.status.value,
            is_active=row.is_active,
        )
        out.append(Person(columns, p, policy, office))
    other_policy = filters.policy_id is not None and (
        default is None or filters.policy_id != default.id
    )
    if filters.department or filters.office_id or other_policy:
        return out
    known = {person.user_id for person in out}
    unprofiled = await LeaveReportRepository(db, org_id=org_id).members_without_profile(ids)
    extra = [u for u in {*unprofiled, *requesters} if u not in known and (ids is None or u in ids)]
    for user in await UserRepository(db).get_many_by_ids(extra):
        columns = PersonColumns(
            user_id=user.id,
            name=user.name,
            employee_code=None,
            department=None,
            office=None,
            policy=default.name if default else None,
            manager=None,
            status=None,
            is_active=user.is_active,
        )
        out.append(Person(columns, None, default))
    return sorted(out, key=lambda person: person.columns.name.lower())
