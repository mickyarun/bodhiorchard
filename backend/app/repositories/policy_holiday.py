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
"""Data access for leave-policy holidays."""

import uuid
from collections.abc import Collection, Sequence
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.policy_holiday import HolidayKind, PolicyHoliday
from app.repositories.base import BaseRepository


class PolicyHolidayRepository(BaseRepository[PolicyHoliday]):
    """Policy holidays, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(PolicyHoliday, db, org_id=org_id)

    async def list_between(
        self,
        policy_id: uuid.UUID,
        start: date,
        end: date,
        *,
        kind: HolidayKind | None = None,
    ) -> list[PolicyHoliday]:
        """A policy's holidays from ``start`` to ``end``, by date."""
        stmt = self._scoped(
            select(PolicyHoliday).where(
                PolicyHoliday.policy_id == policy_id,
                PolicyHoliday.date >= start,
                PolicyHoliday.date <= end,
            )
        )
        if kind is not None:
            stmt = stmt.where(PolicyHoliday.kind == kind)
        result = await self._db.execute(stmt.order_by(PolicyHoliday.date))
        return list(result.scalars().all())

    async def existing_dates(self, policy_id: uuid.UUID, dates: Sequence[date]) -> set[date]:
        """Which of ``dates`` already have a holiday on the policy."""
        if not dates:
            return set()
        stmt = self._scoped(
            select(PolicyHoliday.date).where(
                PolicyHoliday.policy_id == policy_id, PolicyHoliday.date.in_(dates)
            )
        )
        return set((await self._db.execute(stmt)).scalars().all())

    async def by_ids(self, ids: Collection[uuid.UUID]) -> dict[uuid.UUID, PolicyHoliday]:
        """Rows for ``ids`` in this org, keyed by id."""
        if not ids:
            return {}
        result = await self._db.execute(
            self._scoped(select(PolicyHoliday).where(PolicyHoliday.id.in_(ids)))
        )
        return {row.id: row for row in result.scalars().all()}

    def add_staged(self, holiday: PolicyHoliday) -> None:
        """Stage a holiday for insert (caller flushes once for a batch)."""
        self._db.add(holiday)
