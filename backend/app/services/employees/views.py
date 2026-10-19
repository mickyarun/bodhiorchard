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

"""Assemble employee responses from the sections a caller may see."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.user import User
from app.repositories.employee_profile import DirectoryRow
from app.repositories.employee_reporting_manager import (
    EmployeeReportingManagerRepository,
    ManagerLink,
)
from app.schemas.employee import (
    DirectoryEntry,
    EmployeeAccessRead,
    EmployeePersonal,
    EmployeeRead,
    EmployeeWork,
    ManagerRef,
)
from app.services.employees.access import EmployeeAccess


def _manager_ref(link: ManagerLink) -> ManagerRef:
    return ManagerRef(
        user_id=link.user_id, name=link.name, is_primary=link.is_primary, is_active=link.is_active
    )


async def employee_read(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    profile: EmployeeProfile,
    user: User,
    access: EmployeeAccess,
    access_revoked: bool | None = None,
) -> EmployeeRead:
    """Build an :class:`EmployeeRead`, including personal fields only if allowed."""
    links = await EmployeeReportingManagerRepository(db, org_id=org_id).list_for_profiles(
        [profile.id]
    )
    return EmployeeRead(
        user_id=user.id,
        profile_id=profile.id,
        name=user.name,
        email=user.email,
        is_active=user.is_active,
        work=EmployeeWork.model_validate(profile),
        managers=[_manager_ref(link) for link in links.get(profile.id, [])],
        personal=EmployeePersonal.model_validate(profile) if access.view_personal else None,
        access=EmployeeAccessRead(
            edit_work=access.edit_work,
            edit_personal=access.edit_personal,
            edit_managers=access.edit_managers,
        ),
        access_revoked=access_revoked,
    )


async def directory_entries(
    db: AsyncSession, *, org_id: uuid.UUID, rows: list[DirectoryRow]
) -> list[DirectoryEntry]:
    """Directory rows with each employee's primary manager."""
    links = await EmployeeReportingManagerRepository(db, org_id=org_id).list_for_profiles(
        [row.profile.id for row in rows]
    )
    entries = []
    for row in rows:
        managers = links.get(row.profile.id, [])
        primary = next((m for m in managers if m.is_primary), None)
        entries.append(
            DirectoryEntry(
                user_id=row.profile.user_id,
                name=row.name,
                email=row.email,
                is_active=row.is_active,
                employee_code=row.profile.employee_code,
                designation=row.profile.designation,
                department=row.profile.department,
                status=row.profile.status,
                primary_manager=_manager_ref(primary) if primary else None,
                manager_count=len(managers),
            )
        )
    return entries
