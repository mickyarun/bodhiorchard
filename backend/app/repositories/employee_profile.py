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

"""Data access for employee profiles (one per org member)."""

import uuid
from dataclasses import dataclass

from sqlalchemy import or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile, EmployeeStatus
from app.models.user import OrgToUser, User
from app.repositories.base import BaseRepository, rowcount


@dataclass(frozen=True)
class DirectoryRow:
    """A profile with the member fields the directory shows."""

    profile: EmployeeProfile
    name: str
    email: str
    is_active: bool


@dataclass(frozen=True)
class MemberSummary:
    """A member who could be given an employee record."""

    user_id: uuid.UUID
    name: str
    email: str


class EmployeeProfileRepository(BaseRepository[EmployeeProfile]):
    """Employee profiles, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Tenant whose profiles this repository exposes.
        """
        super().__init__(EmployeeProfile, db, org_id=org_id)
        self._org = org_id

    async def get_by_user(self, user_id: uuid.UUID) -> EmployeeProfile | None:
        """The profile for ``user_id`` in this org, if any."""
        result = await self._db.execute(
            self._scoped(select(EmployeeProfile).where(EmployeeProfile.user_id == user_id))
        )
        return result.scalar_one_or_none()

    async def code_taken(self, code: str, *, exclude_profile: uuid.UUID | None) -> bool:
        """True if another profile in this org already uses ``code``."""
        stmt = self._scoped(
            select(EmployeeProfile.id).where(EmployeeProfile.employee_code == code)
        )
        if exclude_profile is not None:
            stmt = stmt.where(EmployeeProfile.id != exclude_profile)
        return (await self._db.execute(stmt)).first() is not None

    async def list_directory(
        self,
        *,
        search: str | None = None,
        department: str | None = None,
        status: EmployeeStatus | None = None,
    ) -> list[DirectoryRow]:
        """Profiles joined to their member, ordered by name."""
        stmt = (
            select(EmployeeProfile, User.name, User.email, User.is_active)
            .join(User, User.id == EmployeeProfile.user_id)
            .where(EmployeeProfile.org_id == self._org)
            .order_by(User.name)
        )
        if search:
            # Escape LIKE wildcards so "%" or "_" in a search match literally.
            term = search.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{term}%"
            stmt = stmt.where(
                or_(
                    User.name.ilike(pattern, escape="\\"),
                    User.email.ilike(pattern, escape="\\"),
                    EmployeeProfile.employee_code.ilike(pattern, escape="\\"),
                    EmployeeProfile.designation.ilike(pattern, escape="\\"),
                )
            )
        if department:
            stmt = stmt.where(EmployeeProfile.department == department)
        if status is not None:
            stmt = stmt.where(EmployeeProfile.status == status)
        rows = (await self._db.execute(stmt)).all()
        return [DirectoryRow(profile=r[0], name=r[1], email=r[2], is_active=r[3]) for r in rows]

    async def list_members_without_profile(self) -> list[MemberSummary]:
        """Active org members who don't have an employee record yet."""
        stmt = (
            select(User.id, User.name, User.email)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .outerjoin(
                EmployeeProfile,
                (EmployeeProfile.user_id == User.id) & (EmployeeProfile.org_id == self._org),
            )
            .where(
                OrgToUser.org_id == self._org,
                User.is_active.is_(True),
                EmployeeProfile.id.is_(None),
            )
            .order_by(User.name)
        )
        rows = (await self._db.execute(stmt)).all()
        return [MemberSummary(user_id=r[0], name=r[1], email=r[2]) for r in rows]

    async def repoint_user(self, source: uuid.UUID, target: uuid.UUID) -> int:
        """Move ``source``'s profile to ``target`` (member merge)."""
        result = await self._db.execute(
            sql_update(EmployeeProfile)
            .where(EmployeeProfile.org_id == self._org, EmployeeProfile.user_id == source)
            .values(user_id=target)
        )
        return rowcount(result) or 0
