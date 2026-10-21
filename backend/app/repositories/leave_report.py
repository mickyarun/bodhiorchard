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

"""Data access for leave reports: requests in a range and the people reported on.

Profiles are joined on this org only: a user can have a profile in another
org too, and its department or office must never leak into this one.
"""

import uuid
from collections import defaultdict
from collections.abc import Collection, Mapping
from dataclasses import dataclass
from datetime import date

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.models.user import OrgToUser, User
from app.repositories.base import BaseRepository
from app.repositories.leave_request_filter import RequestFilter, apply_filter


@dataclass(frozen=True)
class ProfileRow:
    """A member with an employee profile in this org."""

    profile: EmployeeProfile
    name: str
    is_active: bool


class LeaveReportRepository(BaseRepository[LeaveRequest]):
    """Report reads, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(LeaveRequest, db, org_id=org_id)

    async def overlapping(
        self,
        user_ids: Collection[uuid.UUID] | None,
        start: date,
        end: date,
        filters: RequestFilter | None,
        *,
        limit: int,
    ) -> list[LeaveRequest]:
        """Requests overlapping ``start..end``, by start date; at most ``limit``."""
        if user_ids is not None and not user_ids:
            return []
        stmt = self._scoped(
            select(LeaveRequest).where(
                LeaveRequest.start_date <= end, LeaveRequest.end_date >= start
            )
        )
        stmt = apply_filter(stmt, filters)
        if user_ids is not None:
            stmt = stmt.where(LeaveRequest.user_id.in_(user_ids))
        stmt = stmt.order_by(LeaveRequest.start_date, LeaveRequest.created_at).limit(limit)
        return list((await self._db.execute(stmt)).scalars().all())

    async def profiles(
        self,
        user_ids: Collection[uuid.UUID] | None,
        *,
        department: str | None = None,
        office_id: uuid.UUID | None = None,
        policy_id: uuid.UUID | None = None,
        policy_is_default: bool = False,
    ) -> list[ProfileRow]:
        """Members with a profile here, by name.

        ``policy_id`` matches the member's current policy; with
        ``policy_is_default`` it also matches profiles that follow the default.
        """
        if user_ids is not None and not user_ids:
            return []
        stmt = (
            select(EmployeeProfile, User.name, User.is_active)
            .join(User, User.id == EmployeeProfile.user_id)
            .where(EmployeeProfile.org_id == self._org_id)
            .order_by(User.name)
        )
        if user_ids is not None:
            stmt = stmt.where(EmployeeProfile.user_id.in_(user_ids))
        if department:
            stmt = stmt.where(EmployeeProfile.department == department)
        if office_id is not None:
            stmt = stmt.where(EmployeeProfile.office_id == office_id)
        if policy_id is not None:
            match = EmployeeProfile.leave_policy_id == policy_id
            if policy_is_default:
                match = or_(match, EmployeeProfile.leave_policy_id.is_(None))
            stmt = stmt.where(match)
        rows = (await self._db.execute(stmt)).all()
        return [ProfileRow(p, name, active) for p, name, active in rows]

    async def members_without_profile(
        self, user_ids: Collection[uuid.UUID] | None
    ) -> list[uuid.UUID]:
        """Active members of this org with no profile here (they follow the default policy)."""
        if user_ids is not None and not user_ids:
            return []
        has_profile = select(EmployeeProfile.user_id).where(EmployeeProfile.org_id == self._org_id)
        stmt = (
            select(User.id)
            .join(OrgToUser, OrgToUser.user_id == User.id)
            .where(
                OrgToUser.org_id == self._org_id,
                User.is_active.is_(True),
                User.id.not_in(has_profile),
            )
        )
        if user_ids is not None:
            stmt = stmt.where(User.id.in_(user_ids))
        return list((await self._db.execute(stmt)).scalars().all())

    async def with_profile(self, user_ids: Collection[uuid.UUID]) -> set[uuid.UUID]:
        """Which of ``user_ids`` have an employee profile in this org."""
        if not user_ids:
            return set()
        stmt = select(EmployeeProfile.user_id).where(
            EmployeeProfile.org_id == self._org_id, EmployeeProfile.user_id.in_(user_ids)
        )
        return set((await self._db.execute(stmt)).scalars().all())

    async def last_taken(self, cutoffs: Mapping[uuid.UUID, date]) -> list[LeaveRequest]:
        """Each member's most recent approved leave starting by their own cutoff.

        ``cutoffs`` maps member to "today" on their policy, so a leave that
        started today locally counts even before it is today in UTC.
        """
        if not cutoffs:
            return []
        by_day: dict[date, set[uuid.UUID]] = defaultdict(set)
        for user_id, day in cutoffs.items():
            by_day[day].add(user_id)
        started = or_(
            *(
                and_(LeaveRequest.user_id.in_(users), LeaveRequest.start_date <= day)
                for day, users in by_day.items()
            )
        )
        stmt = (
            self._scoped(select(LeaveRequest))
            .where(
                started,
                LeaveRequest.kind == LeaveKind.LEAVE,
                LeaveRequest.status == LeaveStatus.APPROVED,
            )
            .distinct(LeaveRequest.user_id)
            .order_by(
                LeaveRequest.user_id,
                LeaveRequest.start_date.desc(),
                LeaveRequest.created_at.desc(),
            )
        )
        return list((await self._db.execute(stmt)).scalars().all())
