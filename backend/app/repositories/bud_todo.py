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

"""Repository for BUD TODO queries + atomic claim operation."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, or_, select, update
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

    async def has_active_or_taken_todos(self, bud_id: uuid.UUID) -> bool:
        """True if any non-checkpoint TODO is in_progress, completed, or taken over.

        Used to gate top-level BUD reassignment: when a developer has already
        claimed (``taken_at IS NOT NULL``) or progressed any TODO, mass-
        reassigning the BUD's TODOs would clobber their work, so the cascade
        is skipped. Checkpoints are excluded — they're inert gating rows.
        """
        stmt = self._scoped(
            select(func.count(BUDTodo.id)).where(
                BUDTodo.bud_id == bud_id,
                BUDTodo.is_checkpoint.is_(False),
                or_(
                    BUDTodo.status.in_(
                        [BUDTodoStatus.IN_PROGRESS.value, BUDTodoStatus.COMPLETED.value]
                    ),
                    BUDTodo.taken_at.is_not(None),
                ),
            )
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one()) > 0

    async def list_non_checkpoint_for_bud(self, bud_id: uuid.UUID) -> list[BUDTodo]:
        """All non-checkpoint TODOs for a BUD, ordered by sequence."""
        stmt = self._scoped(
            select(BUDTodo)
            .where(
                BUDTodo.bud_id == bud_id,
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

    async def phase_completion(self, bud_id: uuid.UUID, phase: str) -> tuple[int, int]:
        """Return ``(completed, total)`` non-checkpoint todos for one phase.

        Drives the estimator's progress-aware discount: a phase whose todos
        are all done shouldn't be re-budgeted at full effort just because the
        BUD hasn't been transitioned yet. Checkpoints are excluded (they're
        inert gating rows, not work). A phase with no todos returns ``(0, 0)``
        so the caller can treat "no signal" distinctly from "nothing done".
        """
        stmt = self._scoped(
            select(
                func.count().filter(BUDTodo.status == BUDTodoStatus.COMPLETED.value),
                func.count(),
            ).where(
                BUDTodo.bud_id == bud_id,
                BUDTodo.phase == phase,
                BUDTodo.is_checkpoint.is_(False),
            )
        )
        row = (await self._db.execute(stmt)).one()
        return int(row[0]), int(row[1])

    async def completed_assignee_counts(self, bud_id: uuid.UUID) -> dict[uuid.UUID, int]:
        """Per-assignee count of COMPLETED non-checkpoint todos for a BUD.

        Drives the developer BUD-shipped SP split: each assignee's completed
        count is the weight (later scaled by the substance judge). Rows with a
        NULL assignee are excluded. Returns an empty dict when nobody completed
        an assigned todo (callers then fall back to all-assigned, then commits).
        """
        stmt = self._scoped(
            select(BUDTodo.assignee_id, func.count(BUDTodo.id))
            .where(
                BUDTodo.bud_id == bud_id,
                BUDTodo.status == BUDTodoStatus.COMPLETED.value,
                BUDTodo.is_checkpoint.is_(False),
                BUDTodo.assignee_id.is_not(None),
            )
            .group_by(BUDTodo.assignee_id)
        )
        result = await self._db.execute(stmt)
        return {row[0]: int(row[1]) for row in result.all() if row[0] is not None}

    async def assigned_distinct_assignees(self, bud_id: uuid.UUID) -> set[uuid.UUID]:
        """Distinct assignees across ALL assigned non-checkpoint todos (any status).

        The fallback recipient set when no todo reached COMPLETED but work was
        clearly assigned.
        """
        stmt = self._scoped(
            select(BUDTodo.assignee_id)
            .where(
                BUDTodo.bud_id == bud_id,
                BUDTodo.is_checkpoint.is_(False),
                BUDTodo.assignee_id.is_not(None),
            )
            .distinct()
        )
        result = await self._db.execute(stmt)
        return {row[0] for row in result.all() if row[0] is not None}

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

    async def next_sequence(self, bud_id: uuid.UUID) -> int:
        """Return the next unused sequence for a BUD (``max(sequence) + 1``, or 1)."""
        stmt = self._scoped(select(func.max(BUDTodo.sequence)).where(BUDTodo.bud_id == bud_id))
        result = await self._db.execute(stmt)
        return (result.scalar_one_or_none() or 0) + 1

    async def create_todo(
        self,
        bud_id: uuid.UUID,
        *,
        title: str,
        phase: str,
        description: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> BUDTodo:
        """Insert a PENDING, unassigned, non-checkpoint TODO at the next sequence.

        Backs the manual "add todo" REST endpoint and the ``create_todo`` MCP
        tool. ``detail`` carries the ``{"source": "manual"}`` marker that keeps
        the row from being deleted by the tech-spec reconciler — see
        ``todo_sync._is_preserved``. Callers re-fetch via ``get_by_sequence`` to
        pick up the eager-loaded assignee for serialization.
        """
        todo = BUDTodo(
            org_id=self._org_id,
            bud_id=bud_id,
            sequence=await self.next_sequence(bud_id),
            title=title,
            phase=phase,
            status=BUDTodoStatus.PENDING.value,
            is_checkpoint=False,
            description=description,
            detail=detail,
        )
        self._db.add(todo)
        await self._db.flush()
        return todo
