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

"""Leave days used and pending, summed for balances.

Balances count paid days only: a request's loss-of-pay days are left out.

Kept apart from :mod:`app.repositories.leave_request` (which reads and
transitions single requests) so the aggregates for balances live together.
"""

import uuid
from collections.abc import Collection
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_request import LeaveKind, LeaveRequest, LeaveStatus
from app.repositories.base import BaseRepository
from app.repositories.leave_request import ACTIVE

ZERO = Decimal("0")
PAID_DAYS = LeaveRequest.days - LeaveRequest.lop_days
UsageRow = tuple[uuid.UUID, uuid.UUID, LeaveStatus, date, Decimal]
LopRow = tuple[uuid.UUID, date, Decimal]


class LeaveUsageRepository(BaseRepository[LeaveRequest]):
    """Sums of leave days, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(LeaveRequest, db, org_id=org_id)

    async def leave_day_totals(
        self, user_id: uuid.UUID, start: date, end: date
    ) -> dict[uuid.UUID, tuple[Decimal, Decimal]]:
        """``{leave_type_id: (approved_days, pending_days)}`` for a leave year."""
        stmt = self._scoped(
            select(LeaveRequest.leave_type_id, LeaveRequest.status, func.sum(PAID_DAYS))
            .where(
                LeaveRequest.user_id == user_id,
                LeaveRequest.kind == LeaveKind.LEAVE,
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.start_date >= start,
                LeaveRequest.start_date <= end,
            )
            .group_by(LeaveRequest.leave_type_id, LeaveRequest.status)
        )
        totals: dict[uuid.UUID, tuple[Decimal, Decimal]] = {}
        for type_id, status, days in (await self._db.execute(stmt)).all():
            approved, pending = totals.get(type_id, (ZERO, ZERO))
            if status == LeaveStatus.APPROVED:
                approved += days
            else:
                pending += days
            totals[type_id] = (approved, pending)
        return totals

    async def lop_total(self, user_id: uuid.UUID, start: date, end: date) -> Decimal:
        """Loss-of-pay days on approved and pending leave starting in a leave year."""
        stmt = self._scoped(
            select(func.coalesce(func.sum(LeaveRequest.lop_days), ZERO)).where(
                LeaveRequest.user_id == user_id,
                LeaveRequest.kind == LeaveKind.LEAVE,
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.start_date >= start,
                LeaveRequest.start_date <= end,
            )
        )
        return Decimal((await self._db.execute(stmt)).scalar_one())

    async def open_with_lop(
        self, user_id: uuid.UUID, leave_type_id: uuid.UUID, start: date, end: date
    ) -> list[LeaveRequest]:
        """Approved and pending leave of one type in a leave year that has loss of pay.

        Oldest first, so days freed up go to the earliest leave.
        """
        stmt = self._scoped(
            select(LeaveRequest)
            .where(
                LeaveRequest.user_id == user_id,
                LeaveRequest.leave_type_id == leave_type_id,
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.lop_days > 0,
                LeaveRequest.start_date >= start,
                LeaveRequest.start_date <= end,
            )
            .order_by(LeaveRequest.start_date, LeaveRequest.created_at)
        )
        return list((await self._db.scalars(stmt)).all())

    async def holiday_booked(self, holiday_id: uuid.UUID) -> bool:
        """Whether any approved or pending request books this optional holiday."""
        stmt = self._scoped(
            select(LeaveRequest.id).where(
                LeaveRequest.holiday_id == holiday_id, LeaveRequest.status.in_(ACTIVE)
            )
        ).limit(1)
        return (await self._db.execute(stmt)).first() is not None

    async def leave_days_by_start(
        self,
        user_ids: Collection[uuid.UUID],
        type_ids: Collection[uuid.UUID],
        start: date,
        end: date,
    ) -> list[UsageRow]:
        """Active leave days per member, type, status and start date.

        For pricing many members at once: callers bucket the rows into each
        member's own leave year.
        """
        if not user_ids or not type_ids:
            return []
        stmt = self._scoped(
            select(
                LeaveRequest.user_id,
                LeaveRequest.leave_type_id,
                LeaveRequest.status,
                LeaveRequest.start_date,
                func.sum(PAID_DAYS),
            )
            .where(
                LeaveRequest.user_id.in_(user_ids),
                LeaveRequest.leave_type_id.in_(type_ids),
                LeaveRequest.kind == LeaveKind.LEAVE,
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.start_date >= start,
                LeaveRequest.start_date <= end,
            )
            .group_by(
                LeaveRequest.user_id,
                LeaveRequest.leave_type_id,
                LeaveRequest.status,
                LeaveRequest.start_date,
            )
        )
        rows = (await self._db.execute(stmt)).all()
        return [(user, kind, status, day, days) for user, kind, status, day, days in rows]

    async def lop_by_start(
        self, user_ids: Collection[uuid.UUID], start: date, end: date
    ) -> list[LopRow]:
        """Active loss-of-pay days per member and start date, for many members.

        Callers bucket the rows into each member's own leave year, as with
        :meth:`leave_days_by_start`.
        """
        if not user_ids:
            return []
        stmt = self._scoped(
            select(LeaveRequest.user_id, LeaveRequest.start_date, func.sum(LeaveRequest.lop_days))
            .where(
                LeaveRequest.user_id.in_(user_ids),
                LeaveRequest.status.in_(ACTIVE),
                LeaveRequest.lop_days > 0,
                LeaveRequest.start_date >= start,
                LeaveRequest.start_date <= end,
            )
            .group_by(LeaveRequest.user_id, LeaveRequest.start_date)
        )
        return [(user, day, lop) for user, day, lop in (await self._db.execute(stmt)).all()]
