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

"""Who may decide a member's requests.

Approvers are the member's *current* active reporting managers — any one
of them may decide, and the first decision wins. With no active manager
the request goes to the HR queue (holders of ``leave:approve``). HR may
also act on any request, but nobody decides their own.
"""

import uuid
from collections.abc import Collection
from dataclasses import dataclass
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.repositories.user import UserRepository

APPROVE = "leave:approve"
Route = Literal["manager", "hr_queue", "hr_override"]


@dataclass(frozen=True)
class Approvers:
    """A member's active managers; empty means "goes to HR"."""

    managers: list[tuple[uuid.UUID, str]]

    @property
    def routes_to_hr(self) -> bool:
        """True when no active manager can decide."""
        return not self.managers

    @property
    def manager_ids(self) -> set[uuid.UUID]:
        """Just the ids."""
        return {user_id for user_id, _ in self.managers}


async def approvers_for_many(
    db: AsyncSession, org_id: uuid.UUID, user_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, Approvers]:
    """Active reporting managers for several members in a few queries.

    "Active" means an active member *of this org*: a manager who left the
    org, or whose account was deactivated, can't decide, so their reports'
    requests route to HR instead of waiting forever.
    """
    profiles = await EmployeeProfileRepository(db, org_id=org_id).by_users(user_ids)
    repo = EmployeeReportingManagerRepository(db, org_id=org_id)
    links = await repo.list_for_profiles([p.id for p in profiles.values()])
    current = await repo.active_member_ids(
        list({link.user_id for group in links.values() for link in group})
    )
    out: dict[uuid.UUID, Approvers] = {}
    for user_id in user_ids:
        profile = profiles.get(user_id)
        group = links.get(profile.id, []) if profile else []
        out[user_id] = Approvers(
            managers=[(link.user_id, link.name) for link in group if link.user_id in current]
        )
    return out


async def approvers_for(db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID) -> Approvers:
    """``user_id``'s active reporting managers."""
    return (await approvers_for_many(db, org_id, [user_id]))[user_id]


async def notify_targets(
    db: AsyncSession, org_id: uuid.UUID, approvers: Approvers, requester: uuid.UUID
) -> set[uuid.UUID]:
    """Who to tell about a new request: the managers, else HR."""
    if approvers.managers:
        return approvers.manager_ids
    hr = await UserRepository(db).list_member_ids_with_permission(org_id, APPROVE)
    return set(hr) - {requester}


def route_for(
    actor: uuid.UUID, perms: PermissionSet, requester: uuid.UUID, approvers: Approvers
) -> Route | None:
    """How ``actor`` may decide this member's request, or None if they can't."""
    if actor == requester:
        return None
    if actor in approvers.manager_ids:
        return "manager"
    if perms.has(APPROVE):
        return "hr_queue" if approvers.routes_to_hr else "hr_override"
    return None


async def reports_of(db: AsyncSession, org_id: uuid.UUID, manager: uuid.UUID) -> set[uuid.UUID]:
    """Members who list ``manager`` as a reporting manager."""
    edges = await EmployeeReportingManagerRepository(db, org_id=org_id).reporting_edges()
    return {employee for employee, boss in edges if boss == manager}
