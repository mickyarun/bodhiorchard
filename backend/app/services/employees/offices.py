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

"""Offices on employee records: checking one, and following its leave policy.

An office can name a leave policy. Putting someone in that office (or
creating them there) moves them onto it, through the same assignment
rules as moving them by hand; HR can still choose another policy after.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.office_location import OfficeLocation
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.office_location import OfficeLocationRepository
from app.schemas.employee import OfficeRef
from app.services.leave import policy_admin


async def check_office(
    db: AsyncSession, org_id: uuid.UUID, office_id: uuid.UUID | None
) -> OfficeLocation | None:
    """The office for a record, or 422 if it isn't one of this org's."""
    if office_id is None:
        return None
    office = await OfficeLocationRepository(db, org_id=org_id).get_by_id(office_id)
    if office is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pick one of your offices."
        )
    return office


async def follow_office_policy(
    db: AsyncSession,
    *,
    profile: EmployeeProfile,
    office: OfficeLocation | None,
    previous_office_id: uuid.UUID | None,
    actor_id: uuid.UUID,
    actor_is_owner: bool,
) -> None:
    """Move ``profile`` onto its new office's policy, if the office names one."""
    if office is None or office.id == previous_office_id or office.leave_policy_id is None:
        return
    policy = await LeavePolicyRepository(db, org_id=profile.org_id).get_by_id(
        office.leave_policy_id
    )
    if policy is None or policy.id == profile.leave_policy_id:
        return
    await policy_admin.assign_employees(
        db, policy, actor_id, [profile.user_id], actor_is_owner=actor_is_owner
    )
    await db.refresh(profile)


async def office_refs(
    db: AsyncSession, org_id: uuid.UUID, office_ids: set[uuid.UUID]
) -> dict[uuid.UUID, OfficeRef]:
    """``{office_id: OfficeRef}`` for display."""
    offices = await OfficeLocationRepository(db, org_id=org_id).by_ids(office_ids)
    return {oid: OfficeRef(id=o.id, name=o.name) for oid, o in offices.items()}
