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

"""Which employees follow a leave policy, and moving them between policies."""

import uuid
from collections.abc import Sequence
from datetime import date

from sqlalchemy import ColumnElement, case, exists, func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_ledger import LeaveLedgerEntry
from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.models.leave_type import LeaveType
from app.models.user import User
from app.repositories.base import rowcount


class LeavePolicyMemberRepository:
    """Policy membership through employee profiles, scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        self._db = db
        self._org = org_id

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
        self, policy: LeavePolicy, user_ids: Sequence[uuid.UUID], on: date
    ) -> int:
        """Move employees' profiles onto ``policy`` from ``on``.

        People already on it — explicitly, or by default when it is the
        default policy — are left alone, so their start date (which drives
        allocation) isn't reset.

        ``on`` only becomes the start date for people with leave history on
        another policy — a real transfer, prorated from the move. Anyone
        else is being set up for the first time, so their joining date keeps
        driving allocation: moving the whole office onto a new policy in
        October mustn't cut everyone to a quarter of their quota.
        """
        not_already = (
            EmployeeProfile.leave_policy_id != policy.id
            if policy.is_default
            else or_(
                EmployeeProfile.leave_policy_id.is_(None),
                EmployeeProfile.leave_policy_id != policy.id,
            )
        )
        result = await self._db.execute(
            sql_update(EmployeeProfile)
            .where(
                EmployeeProfile.org_id == self._org,
                EmployeeProfile.user_id.in_(user_ids),
                not_already,
            )
            .values(
                leave_policy_id=policy.id,
                leave_policy_assigned_on=case((self._has_history_elsewhere(policy), on)),
            )
        )
        return rowcount(result) or 0

    def _has_history_elsewhere(self, policy: LeavePolicy) -> ColumnElement[bool]:
        """The member has leave balance history on another policy.

        A ledger row exists exactly when leave was spent (the allocation is
        frozen on first use) or HR adjusted a balance. WFH and optional
        holidays don't count: the default policy starts with no leave
        types, so people use WFH there long before their real policy exists.
        """
        return exists().where(
            LeaveLedgerEntry.org_id == self._org,
            LeaveLedgerEntry.user_id == EmployeeProfile.user_id,
            LeaveLedgerEntry.leave_type_id == LeaveType.id,
            LeaveType.policy_id != policy.id,
        )

    async def count_pending_elsewhere(
        self, policy: LeavePolicy, user_ids: Sequence[uuid.UUID]
    ) -> int:
        """How many of ``user_ids`` have pending requests made under another policy."""
        if not user_ids:
            return 0
        stmt = select(func.count(func.distinct(LeaveRequest.user_id))).where(
            LeaveRequest.org_id == self._org,
            LeaveRequest.user_id.in_(user_ids),
            LeaveRequest.policy_id != policy.id,
            LeaveRequest.status == LeaveStatus.PENDING,
        )
        return int((await self._db.execute(stmt)).scalar() or 0)
