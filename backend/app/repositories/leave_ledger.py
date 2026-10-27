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

"""Data access for the leave balance ledger."""

import uuid
from collections.abc import Collection
from decimal import Decimal

from sqlalchemy import case, func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_ledger import LeaveLedgerEntry, LedgerEntryType
from app.repositories.base import BaseRepository
from app.repositories.leave_ledger_totals import YearTotals, split_totals

# Each entry type's days summed apart by sign: added and taken-away days
# count differently (see :class:`YearTotals`).
_PLUS = func.sum(case((LeaveLedgerEntry.days > 0, LeaveLedgerEntry.days), else_=0))
_MINUS = func.sum(case((LeaveLedgerEntry.days < 0, LeaveLedgerEntry.days), else_=0))
_YearKey = tuple[uuid.UUID, uuid.UUID, int]


class LeaveLedgerRepository(BaseRepository[LeaveLedgerEntry]):
    """Ledger entries, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(LeaveLedgerEntry, db, org_id=org_id)
        self._org = org_id

    async def totals(self, user_id: uuid.UUID, leave_year: int) -> dict[uuid.UUID, YearTotals]:
        """``{leave_type_id: totals}`` for one year.

        See :func:`split_totals` for how corrections count.
        """
        stmt = self._scoped(
            select(LeaveLedgerEntry.leave_type_id, LeaveLedgerEntry.entry_type, _PLUS, _MINUS)
            .where(LeaveLedgerEntry.user_id == user_id, LeaveLedgerEntry.leave_year == leave_year)
            .group_by(LeaveLedgerEntry.leave_type_id, LeaveLedgerEntry.entry_type)
        )
        sums: dict[uuid.UUID, dict[LedgerEntryType, tuple[Decimal, Decimal]]] = {}
        for type_id, entry_type, plus, minus in (await self._db.execute(stmt)).all():
            sums.setdefault(type_id, {})[entry_type] = (plus, minus)
        return {key: split_totals(by_type) for key, by_type in sums.items()}

    async def type_totals(
        self, user_ids: Collection[uuid.UUID], type_ids: Collection[uuid.UUID]
    ) -> dict[_YearKey, YearTotals]:
        """``{(user, type, leave_year): totals}``.

        See :func:`split_totals` for how corrections count.
        """
        if not user_ids or not type_ids:
            return {}
        stmt = self._scoped(
            select(
                LeaveLedgerEntry.user_id,
                LeaveLedgerEntry.leave_type_id,
                LeaveLedgerEntry.leave_year,
                LeaveLedgerEntry.entry_type,
                _PLUS,
                _MINUS,
            )
            .where(
                LeaveLedgerEntry.user_id.in_(user_ids),
                LeaveLedgerEntry.leave_type_id.in_(type_ids),
            )
            .group_by(
                LeaveLedgerEntry.user_id,
                LeaveLedgerEntry.leave_type_id,
                LeaveLedgerEntry.leave_year,
                LeaveLedgerEntry.entry_type,
            )
        )
        sums: dict[_YearKey, dict[LedgerEntryType, tuple[Decimal, Decimal]]] = {}
        for user_id, type_id, year, kind, plus, minus in (await self._db.execute(stmt)).all():
            sums.setdefault((user_id, type_id, year), {})[kind] = (plus, minus)
        return {key: split_totals(by_type) for key, by_type in sums.items()}

    async def allocated_since(self, leave_type_id: uuid.UUID, leave_year: int) -> bool:
        """True if anyone's allocation for ``leave_year`` or later is already booked."""
        stmt = self._scoped(
            select(LeaveLedgerEntry.id)
            .where(
                LeaveLedgerEntry.leave_type_id == leave_type_id,
                LeaveLedgerEntry.leave_year >= leave_year,
                LeaveLedgerEntry.entry_type == LedgerEntryType.ALLOCATION,
            )
            .limit(1)
        )
        return (await self._db.execute(stmt)).first() is not None

    async def frozen_allocation(
        self, user_id: uuid.UUID, leave_type_id: uuid.UUID, leave_year: int
    ) -> tuple[Decimal | None, Decimal]:
        """``(allocation or None, sum of corrections)`` for one type and year."""
        stmt = self._scoped(
            select(LeaveLedgerEntry.entry_type, func.sum(LeaveLedgerEntry.days))
            .where(
                LeaveLedgerEntry.user_id == user_id,
                LeaveLedgerEntry.leave_type_id == leave_type_id,
                LeaveLedgerEntry.leave_year == leave_year,
                LeaveLedgerEntry.entry_type.in_(
                    (LedgerEntryType.ALLOCATION, LedgerEntryType.CORRECTION)
                ),
            )
            .group_by(LeaveLedgerEntry.entry_type)
        )
        sums = dict((await self._db.execute(stmt)).tuples().all())
        return sums.get(LedgerEntryType.ALLOCATION), sums.get(
            LedgerEntryType.CORRECTION, Decimal("0")
        )

    async def ensure_allocation(
        self, user_id: uuid.UUID, leave_type_id: uuid.UUID, leave_year: int, days: Decimal
    ) -> None:
        """Write the year's allocation once; a concurrent writer wins quietly."""
        stmt = (
            insert(LeaveLedgerEntry)
            .values(
                id=uuid.uuid4(),
                org_id=self._org,
                user_id=user_id,
                leave_type_id=leave_type_id,
                leave_year=leave_year,
                entry_type=LedgerEntryType.ALLOCATION,
                days=days,
                note="Yearly allocation",
            )
            .on_conflict_do_nothing(
                index_elements=["user_id", "leave_type_id", "leave_year"],
                index_where=text("entry_type = 'allocation'"),
            )
        )
        await self._db.execute(stmt)

    async def carried(
        self,
        user_ids: Collection[uuid.UUID],
        type_ids: Collection[uuid.UUID],
        leave_years: Collection[int],
    ) -> set[tuple[uuid.UUID, uuid.UUID, int]]:
        """``(user, type, leave_year)`` that already had days carried into them.

        Only the credit counts: a carry's matching debit sits in the year the
        days left, which may itself be a year carried into.
        """
        if not user_ids or not type_ids or not leave_years:
            return set()
        stmt = self._scoped(
            select(
                LeaveLedgerEntry.user_id,
                LeaveLedgerEntry.leave_type_id,
                LeaveLedgerEntry.leave_year,
            ).where(
                LeaveLedgerEntry.entry_type == LedgerEntryType.CARRY_FORWARD,
                LeaveLedgerEntry.days > 0,
                LeaveLedgerEntry.user_id.in_(user_ids),
                LeaveLedgerEntry.leave_type_id.in_(type_ids),
                LeaveLedgerEntry.leave_year.in_(leave_years),
            )
        )
        return {
            (user, type_id, year) for user, type_id, year in (await self._db.execute(stmt)).all()
        }

    async def list_for(self, user_id: uuid.UUID, leave_year: int) -> list[LeaveLedgerEntry]:
        """A member's entries for one year, oldest first."""
        stmt = self._scoped(
            select(LeaveLedgerEntry)
            .where(LeaveLedgerEntry.user_id == user_id, LeaveLedgerEntry.leave_year == leave_year)
            .order_by(LeaveLedgerEntry.created_at)
        )
        return list((await self._db.execute(stmt)).scalars().all())
