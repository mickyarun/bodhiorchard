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

"""What a viewer can report on: people, departments, offices, policies, types."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.office_location import OfficeLocationRepository
from app.schemas.leave import PersonRef
from app.schemas.leave_report_filters import PeopleFilters
from app.schemas.leave_reports import NamedRef, ReportScopeRead
from app.services.leave.report_scope import ReportScope
from app.services.leave.reports.population import people
from app.services.leave.reports.summary import type_refs


async def scope_options(
    db: AsyncSession, org_id: uuid.UUID, scope: ReportScope
) -> ReportScopeRead:
    """Filter choices limited to what ``scope`` covers."""
    persons = await people(db, org_id, scope.user_ids, PeopleFilters())
    office_ids = {p.profile.office_id for p in persons if p.profile and p.profile.office_id}
    offices = await OfficeLocationRepository(db, org_id=org_id).by_ids(office_ids)
    policies = {p.policy.id: p.policy for p in persons if p.policy}
    type_repo = LeaveTypeRepository(db, org_id=org_id)
    types = [t for pid in policies for t in await type_repo.list_for_policy(pid, active_only=True)]
    names = {pid: policy.name for pid, policy in policies.items()}
    return ReportScopeRead(
        all=scope.is_all,
        people=[PersonRef(user_id=p.user_id, name=p.columns.name) for p in persons],
        departments=sorted({p.columns.department for p in persons if p.columns.department}),
        offices=sorted(
            (NamedRef(id=o.id, name=o.name) for o in offices.values()), key=lambda o: o.name
        ),
        policies=sorted(
            (NamedRef(id=pid, name=name) for pid, name in names.items()), key=lambda p: p.name
        ),
        leave_types=type_refs(sorted(types, key=lambda t: t.name.lower()), names),
    )
