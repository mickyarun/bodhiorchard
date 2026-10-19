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

"""Data access for employee → reporting-manager links."""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import and_, delete, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.employee_profile import EmployeeProfile
from app.models.employee_reporting_manager import EmployeeReportingManager
from app.models.user import OrgToUser, User
from app.repositories.base import BaseRepository, rowcount


@dataclass(frozen=True)
class ManagerLink:
    """A manager of one employee, with display fields."""

    profile_id: uuid.UUID
    user_id: uuid.UUID
    name: str
    is_primary: bool
    is_active: bool


class EmployeeReportingManagerRepository(BaseRepository[EmployeeReportingManager]):
    """Reporting-manager links, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Tenant whose links this repository exposes.
        """
        super().__init__(EmployeeReportingManager, db, org_id=org_id)
        self._org = org_id

    async def list_for_profiles(
        self, profile_ids: Sequence[uuid.UUID]
    ) -> dict[uuid.UUID, list[ManagerLink]]:
        """Managers per profile, primary first then by name."""
        if not profile_ids:
            return {}
        stmt = (
            select(
                EmployeeReportingManager.profile_id,
                User.id,
                User.name,
                EmployeeReportingManager.is_primary,
                User.is_active,
            )
            .join(User, User.id == EmployeeReportingManager.manager_user_id)
            .where(
                EmployeeReportingManager.org_id == self._org,
                EmployeeReportingManager.profile_id.in_(profile_ids),
            )
            .order_by(EmployeeReportingManager.is_primary.desc(), User.name)
        )
        out: dict[uuid.UUID, list[ManagerLink]] = {}
        for row in (await self._db.execute(stmt)).all():
            link = ManagerLink(
                profile_id=row[0], user_id=row[1], name=row[2], is_primary=row[3], is_active=row[4]
            )
            out.setdefault(link.profile_id, []).append(link)
        return out

    async def replace_for_profile(
        self, profile_id: uuid.UUID, managers: Sequence[tuple[uuid.UUID, bool]]
    ) -> None:
        """Replace a profile's managers with ``(manager_user_id, is_primary)`` pairs."""
        await self._db.execute(
            delete(EmployeeReportingManager).where(
                EmployeeReportingManager.org_id == self._org,
                EmployeeReportingManager.profile_id == profile_id,
            )
        )
        # Flush the delete first: the partial unique index on is_primary
        # would otherwise see the old and new primary rows together.
        await self._db.flush()
        for manager_id, is_primary in managers:
            self._db.add(
                EmployeeReportingManager(
                    org_id=self._org,
                    profile_id=profile_id,
                    manager_user_id=manager_id,
                    is_primary=is_primary,
                )
            )
        await self._db.flush()

    async def reporting_edges(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """Every ``(employee_user_id, manager_user_id)`` pair in the org."""
        stmt = (
            select(EmployeeProfile.user_id, EmployeeReportingManager.manager_user_id)
            .join(EmployeeProfile, EmployeeProfile.id == EmployeeReportingManager.profile_id)
            .where(EmployeeReportingManager.org_id == self._org)
        )
        return [(row[0], row[1]) for row in (await self._db.execute(stmt)).all()]

    async def active_member_ids(self, user_ids: Sequence[uuid.UUID]) -> set[uuid.UUID]:
        """Which of ``user_ids`` are active members of this org."""
        if not user_ids:
            return set()
        stmt = (
            select(User.id)
            .join(OrgToUser, and_(OrgToUser.user_id == User.id, OrgToUser.org_id == self._org))
            .where(User.id.in_(user_ids), User.is_active.is_(True))
        )
        return set((await self._db.execute(stmt)).scalars().all())

    async def repoint_manager(self, source: uuid.UUID, target: uuid.UUID) -> int:
        """Hand ``source``'s reports to ``target`` (member merge).

        Links that would duplicate an existing ``target`` link, or make
        someone their own manager, are dropped instead of moved.
        """
        existing = aliased(EmployeeReportingManager)
        already_target = (
            select(existing.id)
            .where(
                existing.profile_id == EmployeeReportingManager.profile_id,
                existing.manager_user_id == target,
            )
            .exists()
        )
        targets_own_profile = select(EmployeeProfile.id).where(
            EmployeeProfile.org_id == self._org, EmployeeProfile.user_id == target
        )
        await self._db.execute(
            delete(EmployeeReportingManager).where(
                EmployeeReportingManager.org_id == self._org,
                EmployeeReportingManager.manager_user_id == source,
                already_target | EmployeeReportingManager.profile_id.in_(targets_own_profile),
            )
        )
        result = await self._db.execute(
            sql_update(EmployeeReportingManager)
            .where(
                EmployeeReportingManager.org_id == self._org,
                EmployeeReportingManager.manager_user_id == source,
            )
            .values(manager_user_id=target)
        )
        return rowcount(result) or 0

    async def delete_self_links(self) -> int:
        """Remove any link where an employee is listed as their own manager."""
        own_user = (
            select(EmployeeProfile.user_id)
            .where(EmployeeProfile.id == EmployeeReportingManager.profile_id)
            .scalar_subquery()
        )
        result = await self._db.execute(
            delete(EmployeeReportingManager).where(
                EmployeeReportingManager.org_id == self._org,
                EmployeeReportingManager.manager_user_id == own_user,
            )
        )
        return rowcount(result) or 0

    async def ensure_primaries(self) -> int:
        """Give every profile that has managers but no primary its oldest link.

        Merges drop or move links in bulk and can remove the one marked
        primary; this restores the "exactly one primary" rule afterwards.
        """
        other = aliased(EmployeeReportingManager)
        has_primary = (
            select(other.id)
            .where(other.profile_id == EmployeeReportingManager.profile_id, other.is_primary)
            .exists()
        )
        first_links = (
            select(EmployeeReportingManager.id)
            .distinct(EmployeeReportingManager.profile_id)
            .where(EmployeeReportingManager.org_id == self._org, ~has_primary)
            .order_by(EmployeeReportingManager.profile_id, EmployeeReportingManager.created_at)
        )
        result = await self._db.execute(
            sql_update(EmployeeReportingManager)
            .where(EmployeeReportingManager.id.in_(first_links.scalar_subquery()))
            .values(is_primary=True)
        )
        return rowcount(result) or 0
