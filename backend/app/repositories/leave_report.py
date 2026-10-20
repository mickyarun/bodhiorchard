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
from collections.abc import Collection
from dataclasses import dataclass
from datetime import date

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_request import LeaveRequest
from app.models.user import User
from app.repositories.base import BaseRepository
from app.repositories.leave_request_filter import RequestFilter, apply_filter


@dataclass(frozen=True)
class ProfileRow:
    """A member with an employee profile in this org."""

    profile: EmployeeProfile
    name: str
    email: str
    is_active: bool


class LeaveReportRepository(BaseRepository[LeaveRequest]):
    """Report reads, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(LeaveRequest, db, org_id=org_id)
        self._org = org_id

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
            select(EmployeeProfile, User.name, User.email, User.is_active)
            .join(User, User.id == EmployeeProfile.user_id)
            .where(EmployeeProfile.org_id == self._org)
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
        return [ProfileRow(p, name, email, active) for p, name, email, active in rows]
