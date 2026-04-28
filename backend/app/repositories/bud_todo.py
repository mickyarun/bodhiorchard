# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Repository for BUD TODO queries + atomic claim operation."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bud_todo import BUDTodo, BUDTodoStatus
from app.repositories.base import BaseRepository


class BUDTodoRepository(BaseRepository[BUDTodo]):
    """Data access for ``BUDTodo`` rows."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(BUDTodo, db, org_id=org_id)

    async def list_unassigned_non_checkpoint_for_bud(self, bud_id: uuid.UUID) -> list[BUDTodo]:
        """Pending unassigned non-checkpoint todos for a BUD, ordered by sequence."""
        stmt = self._scoped(
            select(BUDTodo)
            .where(
                BUDTodo.bud_id == bud_id,
                BUDTodo.assignee_id.is_(None),
                BUDTodo.status == BUDTodoStatus.PENDING.value,
                BUDTodo.is_checkpoint.is_(False),
            )
            .order_by(BUDTodo.sequence.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_remaining_for_bud(self, bud_id: uuid.UUID) -> int:
        """Count non-checkpoint todos that are not yet completed for a BUD."""
        stmt = self._scoped(
            select(func.count(BUDTodo.id)).where(
                BUDTodo.bud_id == bud_id,
                BUDTodo.status != BUDTodoStatus.COMPLETED.value,
                BUDTodo.is_checkpoint.is_(False),
            )
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one())

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[BUDTodo]:
        """Return all TODOs for a BUD ordered by sequence, with assignee eager-loaded."""
        stmt = self._scoped(
            select(BUDTodo)
            .where(BUDTodo.bud_id == bud_id)
            .options(selectinload(BUDTodo.assignee))
            .order_by(BUDTodo.sequence.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sequence(self, bud_id: uuid.UUID, sequence: int) -> BUDTodo | None:
        """Fetch a single TODO by (bud_id, sequence)."""
        stmt = self._scoped(
            select(BUDTodo)
            .where(BUDTodo.bud_id == bud_id, BUDTodo.sequence == sequence)
            .options(selectinload(BUDTodo.assignee))
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def atomic_takeover(
        self, bud_id: uuid.UUID, sequence: int, user_id: uuid.UUID
    ) -> BUDTodo | None:
        """Atomically transition PENDING → IN_PROGRESS assigned to *user_id*.

        Uses a single ``UPDATE ... WHERE status = 'pending' RETURNING`` so
        concurrent takeover attempts can't both succeed. Returns the updated
        row, or ``None`` if the TODO wasn't pending (someone else took it, or
        it's already in_progress/completed).
        """
        stmt = (
            update(BUDTodo)
            .where(
                BUDTodo.bud_id == bud_id,
                BUDTodo.sequence == sequence,
                BUDTodo.status == BUDTodoStatus.PENDING.value,
            )
            .values(
                status=BUDTodoStatus.IN_PROGRESS.value,
                assignee_id=user_id,
                taken_at=datetime.now(UTC),
            )
            .returning(BUDTodo)
        )
        if self._org_id is not None:
            stmt = stmt.where(BUDTodo.org_id == self._org_id)
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        if row is not None:
            await self._db.flush()
        return row
