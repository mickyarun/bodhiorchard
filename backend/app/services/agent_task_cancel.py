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

"""Cancellation of in-flight BUD agent tasks.

The cancel endpoint has two responsibilities that the API layer
shouldn't carry directly: distinguish a live job from an orphan, and
keep the DB rows (``bud_agent_tasks`` + ``bud_designs``) consistent
with the in-memory job state after the signal lands.

This module owns that work. The API stays thin: validate inputs,
delegate, and translate :class:`AgentTaskCancelError` into an HTTP
response.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDesign, BUDDesignStatus
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.repositories.bud import BUDDesignRepository
from app.repositories.bud_agent_task import BUDAgentTaskRepository
from app.services.job_queue import cancel_job as cancel_in_memory_job
from app.services.job_queue import is_job_running

logger = structlog.get_logger(__name__)


class AgentTaskCancelError(Exception):
    """Raised when the cancel signal itself fails.

    Distinct from "task already terminal" (which is a normal no-op
    return) — this means we tried to stop a live Claude run and the
    job-queue refused. The API surfaces the message back to the user;
    no DB rows are written so the spinner correctly keeps showing
    while the subprocess is still alive.
    """


async def cancel_task(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    task: BUDAgentTask,
    reason: str,
) -> BUDAgentTask:
    """Cancel a pending/running agent task and flip the related rows.

    Caller is expected to have already validated tenancy + that the
    task is in a non-terminal state. Commits on the supplied session.

    Args:
        db: Async session, tenant-scoped repos are built from it.
        org_id: Caller's organization (passed through to repos).
        task: The agent task row, freshly loaded.
        reason: Human-readable cancel reason (recorded on the row).

    Returns:
        The freshly-refreshed task row.

    Raises:
        AgentTaskCancelError: when signalling the live job blew up;
            callers should surface the message and write nothing.
    """
    job_id = task.job_id
    alive = job_id is not None and is_job_running(job_id)

    if alive and job_id is not None:
        try:
            cancel_in_memory_job(job_id, reason=reason)
        except Exception as exc:
            logger.warning(
                "agent_task_cancel_signal_failed",
                task_id=str(task.id),
                job_id=job_id,
                error=str(exc),
            )
            raise AgentTaskCancelError(str(exc)) from exc

    task_repo = BUDAgentTaskRepository(db, org_id=org_id)
    await task_repo.mark_failed_if_active(task.id, reason)
    if job_id is not None:
        design_repo = BUDDesignRepository(db, org_id=org_id)
        await design_repo.mark_failed_by_job(job_id)
    await db.commit()

    fresh = await task_repo.get_by_id(task.id)

    logger.info(
        "agent_task_cancel",
        task_id=str(task.id),
        bud_id=str(task.bud_id),
        job_id=job_id,
        alive=alive,
    )

    return fresh if fresh is not None else task


def is_task_terminal(task: BUDAgentTask) -> bool:
    """True iff the task is already in a non-cancellable state."""
    return task.status not in (AgentTaskStatus.PENDING, AgentTaskStatus.RUNNING)


async def cancel_design(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    design: BUDDesign,
    reason: str,
) -> BUDDesign:
    """Cancel a single in-flight design generation.

    Each design row in a multi-repo BUD owns its own ``job_id``; the
    parent ``bud_agent_tasks`` row only records one of them ("first
    job wins"). Cancelling at the task level would therefore kill
    only one repo's run, so the UI exposes per-design cancellation
    instead. After flipping this design, advance the parent task's
    state to match: ``COMPLETED`` if at least one design is READY,
    ``FAILED`` if every remaining design is in a non-generating
    terminal state, otherwise leave it alone.

    Args:
        db: Async session for repo work; commits before returning.
        org_id: Caller's organization scope.
        design: The design row, freshly loaded.
        reason: Human-readable cancel reason for the parent task.

    Returns:
        The freshly-refreshed design row.

    Raises:
        AgentTaskCancelError: when signalling the live job blew up;
            callers should surface the message and write nothing.
    """
    job_id = design.job_id
    alive = job_id is not None and is_job_running(job_id)

    if alive and job_id is not None:
        try:
            cancel_in_memory_job(job_id, reason=reason)
        except Exception as exc:
            logger.warning(
                "design_cancel_signal_failed",
                design_id=str(design.id),
                job_id=job_id,
                error=str(exc),
            )
            raise AgentTaskCancelError(str(exc)) from exc

    design_repo = BUDDesignRepository(db, org_id=org_id)
    await design_repo.mark_failed_by_id(design.id)
    await _advance_design_task_state(db, org_id=org_id, bud_id=design.bud_id, reason=reason)
    await db.commit()

    fresh = await design_repo.get_by_id(design.id)

    logger.info(
        "design_cancel",
        design_id=str(design.id),
        bud_id=str(design.bud_id),
        job_id=job_id,
        alive=alive,
    )

    return fresh if fresh is not None else design


async def _advance_design_task_state(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    reason: str,
) -> None:
    """Roll up per-design status into the parent agent task.

    Mirrors the post-run accounting that ``_maybe_complete_design_task``
    does on the happy path: when no design is still ``generating``,
    the task advances to ``COMPLETED`` (if at least one is READY) or
    ``FAILED`` (if every design ended up failed/cancelled). Until then
    the task stays running so other repos in the same batch can
    finish.
    """
    design_repo = BUDDesignRepository(db, org_id=org_id)
    still_generating = await design_repo.count_by_status(bud_id, BUDDesignStatus.GENERATING)
    if still_generating > 0:
        return

    task_repo = BUDAgentTaskRepository(db, org_id=org_id)
    task = await task_repo.get_active_for_bud(bud_id)
    if task is None:
        return

    ready_count = await design_repo.count_by_status(bud_id, BUDDesignStatus.READY)
    if ready_count > 0:
        await task_repo.mark_completed(task.id, {"cancelled_partial": True})
    else:
        await task_repo.mark_failed_if_active(task.id, reason)
