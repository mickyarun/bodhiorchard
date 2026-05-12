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

"""BUD agent task data access repository."""

import uuid
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.repositories.base import BaseRepository, rowcount


async def recover_stuck_agent_tasks(db: AsyncSession) -> int:
    """Mark all pending/running tasks as failed across all orgs.

    Called once on startup to recover from server crashes mid-job.
    This is intentionally cross-tenant — it runs before any
    org-scoped requests are served.

    Args:
        db: Async database session.

    Returns:
        Number of tasks marked as failed.
    """
    stmt = (
        update(BUDAgentTask)
        .where(
            BUDAgentTask.status.in_(
                [
                    AgentTaskStatus.PENDING,
                    AgentTaskStatus.RUNNING,
                ]
            )
        )
        .values(
            status=AgentTaskStatus.FAILED,
            error_message="Server restarted while task was in progress",
        )
    )
    result = await db.execute(stmt)
    await db.flush()
    return rowcount(result) or 0


class BUDAgentTaskRepository(BaseRepository[BUDAgentTask]):
    """Repository for BUD agent tasks, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(BUDAgentTask, db, org_id=org_id)

    async def list_active_with_bud(self, *, limit: int = 20) -> list[BUDAgentTask]:
        """Pending or running tasks with the linked BUD eager-loaded.

        Used by the dashboard tree to render one robot per active task.
        """
        stmt = self._scoped(
            select(BUDAgentTask)
            .options(selectinload(BUDAgentTask.bud))
            .where(BUDAgentTask.status.in_(["pending", "running"]))
            .order_by(BUDAgentTask.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_active_for_bud(self, bud_id: uuid.UUID) -> BUDAgentTask | None:
        """Get the most recent pending or running task for a BUD.

        Args:
            bud_id: The BUD document UUID.

        Returns:
            The active task, or None.
        """
        stmt = self._scoped(
            select(BUDAgentTask)
            .where(BUDAgentTask.bud_id == bud_id)
            .where(
                BUDAgentTask.status.in_(
                    [
                        AgentTaskStatus.PENDING,
                        AgentTaskStatus.RUNNING,
                    ]
                )
            )
            .order_by(BUDAgentTask.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_failed(self, bud_id: uuid.UUID) -> BUDAgentTask | None:
        """Get the most recent failed task for a BUD (for retry UI).

        Args:
            bud_id: The BUD document UUID.

        Returns:
            The most recent failed task, or None.
        """
        stmt = self._scoped(
            select(BUDAgentTask)
            .where(BUDAgentTask.bud_id == bud_id)
            .where(BUDAgentTask.status == AgentTaskStatus.FAILED)
            .order_by(BUDAgentTask.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_completed(self, bud_id: uuid.UUID) -> BUDAgentTask | None:
        """Get the most recent completed task for a BUD.

        Used to suppress stale failed-task display after a successful retry.
        """
        stmt = self._scoped(
            select(BUDAgentTask)
            .where(BUDAgentTask.bud_id == bud_id)
            .where(BUDAgentTask.status == AgentTaskStatus.COMPLETED)
            .order_by(BUDAgentTask.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[BUDAgentTask]:
        """List all agent tasks for a BUD, most recent first."""
        stmt = self._scoped(
            select(BUDAgentTask)
            .where(BUDAgentTask.bud_id == bud_id)
            .order_by(BUDAgentTask.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def mark_running(self, task_id: uuid.UUID, job_id: str) -> None:
        """Mark a task as running with its in-memory job ID.

        Args:
            task_id: The task UUID.
            job_id: The in-memory job queue ID.
        """
        stmt = (
            update(BUDAgentTask)
            .where(BUDAgentTask.id == task_id)
            .where(BUDAgentTask.org_id == self._org_id)
            .values(status=AgentTaskStatus.RUNNING, job_id=job_id)
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def mark_completed(
        self, task_id: uuid.UUID, result_summary: dict[str, Any] | None = None
    ) -> None:
        """Mark a task as completed.

        Args:
            task_id: The task UUID.
            result_summary: Optional structured output data.
        """
        stmt = (
            update(BUDAgentTask)
            .where(BUDAgentTask.id == task_id)
            .where(BUDAgentTask.org_id == self._org_id)
            .values(
                status=AgentTaskStatus.COMPLETED,
                result_summary=result_summary,
                error_message=None,
            )
        )
        await self._db.execute(stmt)
        await self._db.flush()

    async def mark_failed(self, task_id: uuid.UUID, error_message: str) -> None:
        """Mark a task as failed with an error message.

        Args:
            task_id: The task UUID.
            error_message: Description of the failure.
        """
        stmt = (
            update(BUDAgentTask)
            .where(BUDAgentTask.id == task_id)
            .where(BUDAgentTask.org_id == self._org_id)
            .values(
                status=AgentTaskStatus.FAILED,
                error_message=error_message[:500] if error_message else None,
            )
        )
        await self._db.execute(stmt)
        await self._db.flush()
