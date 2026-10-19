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

"""Carry an employee record across a member merge."""

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.services.employees.managers import has_cycle


class EmployeeMergeConflictError(ValueError):
    """Both members have an employee record; HR must reconcile them first."""


@dataclass(frozen=True)
class EmployeeMergeResult:
    """What moved from the source member to the target."""

    profile_moved: bool
    reports_moved: int


async def transfer_employee_record(
    db: AsyncSession, *, org_id: uuid.UUID, source: uuid.UUID, target: uuid.UUID
) -> EmployeeMergeResult:
    """Move ``source``'s profile and direct reports onto ``target``.

    Refuses when both have a profile: picking one silently would lose HR
    data, so the caller has to delete or reconcile one first.
    """
    profiles = EmployeeProfileRepository(db, org_id=org_id)
    managers = EmployeeReportingManagerRepository(db, org_id=org_id)
    source_profile = await profiles.get_by_user(source)
    if source_profile is not None and await profiles.get_by_user(target) is not None:
        raise EmployeeMergeConflictError(
            "Both members have an employee record. Reconcile them in People before merging."
        )
    moved = await profiles.repoint_user(source, target) if source_profile else 0
    reports = await managers.repoint_manager(source, target)
    await managers.delete_self_links()
    if has_cycle(await managers.reporting_edges()):
        # Raised before any other merge step runs; the request rolls back.
        raise EmployeeMergeConflictError(
            "Merging these members would create a reporting loop. "
            "Change their reporting managers in People first."
        )
    await managers.ensure_primaries()
    return EmployeeMergeResult(profile_moved=bool(moved), reports_moved=reports)
