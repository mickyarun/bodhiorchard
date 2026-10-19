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

"""Data access for leave policies."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import ColumnElement, exists, func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveRequest
from app.models.leave_type import LeaveType
from app.models.user import User
from app.repositories.base import BaseRepository, rowcount


class LeavePolicyRepository(BaseRepository[LeavePolicy]):
    """Leave policies, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Tenant whose policies this repository exposes.
        """
        super().__init__(LeavePolicy, db, org_id=org_id)
        self._org = org_id

    async def list_ordered(self) -> list[LeavePolicy]:
        """Default policy first, then by name."""
        result = await self._db.execute(
            self._scoped(select(LeavePolicy)).order_by(
                LeavePolicy.is_default.desc(), LeavePolicy.name
            )
        )
        return list(result.scalars().all())

    async def get_default(self) -> LeavePolicy | None:
        """The org's default policy, if one exists."""
        result = await self._db.execute(
            self._scoped(select(LeavePolicy).where(LeavePolicy.is_default.is_(True)))
        )
        return result.scalar_one_or_none()

    async def clear_default(self) -> None:
        """Unset the default flag (before setting a new default)."""
        await self._db.execute(
            sql_update(LeavePolicy)
            .where(LeavePolicy.org_id == self._org, LeavePolicy.is_default.is_(True))
            .values(is_default=False)
        )
        await self._db.flush()

    async def name_taken(self, name: str, *, exclude: uuid.UUID | None) -> bool:
        """True if another policy in this org uses ``name``."""
        stmt = self._scoped(select(LeavePolicy.id).where(LeavePolicy.name == name))
        if exclude is not None:
            stmt = stmt.where(LeavePolicy.id != exclude)
        return (await self._db.execute(stmt)).first() is not None

    async def has_requests(self, policy_id: uuid.UUID) -> bool:
        """True once any request was made under the policy."""
        stmt = select(exists().where(LeaveRequest.policy_id == policy_id))
        return bool((await self._db.execute(stmt)).scalar())

    def _follows(self, policy: LeavePolicy) -> ColumnElement[bool]:
        """Profiles on ``policy`` — explicitly, or by default."""
        if policy.is_default:
            return or_(
                EmployeeProfile.leave_policy_id == policy.id,
                EmployeeProfile.leave_policy_id.is_(None),
            )
        return EmployeeProfile.leave_policy_id == policy.id

    async def count_employees(self, policy: LeavePolicy) -> int:
        """Employees following ``policy``."""
        stmt = select(func.count(EmployeeProfile.id)).where(
            EmployeeProfile.org_id == self._org, self._follows(policy)
        )
        return int((await self._db.execute(stmt)).scalar() or 0)

    async def list_employees(self, policy: LeavePolicy) -> list[tuple[uuid.UUID, str]]:
        """``(user_id, name)`` of employees following ``policy``."""
        stmt = (
            select(User.id, User.name)
            .join(EmployeeProfile, EmployeeProfile.user_id == User.id)
            .where(EmployeeProfile.org_id == self._org, self._follows(policy))
            .order_by(User.name)
        )
        return [(row[0], row[1]) for row in (await self._db.execute(stmt)).all()]

    async def assign_employees(
        self, policy_id: uuid.UUID, user_ids: Sequence[uuid.UUID], on: date
    ) -> int:
        """Move employees' profiles onto ``policy_id`` from ``on``."""
        result = await self._db.execute(
            sql_update(EmployeeProfile)
            .where(
                EmployeeProfile.org_id == self._org,
                EmployeeProfile.user_id.in_(user_ids),
                or_(
                    EmployeeProfile.leave_policy_id.is_(None),
                    EmployeeProfile.leave_policy_id != policy_id,
                ),
            )
            .values(leave_policy_id=policy_id, leave_policy_assigned_on=on)
        )
        return rowcount(result) or 0

    async def in_use(self, policy_id: uuid.UUID) -> bool:
        """True if employees, types or requests reference the policy."""
        checks = (
            exists().where(EmployeeProfile.leave_policy_id == policy_id),
            exists().where(LeaveType.policy_id == policy_id),
            exists().where(LeaveRequest.policy_id == policy_id),
        )
        for check in checks:
            if (await self._db.execute(select(check))).scalar():
                return True
        return False
