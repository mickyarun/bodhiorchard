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

"""Async job queue with registry-based worker pools.

Provides a generic queue infrastructure that any service can register
job types with. Workers are spawned at startup based on registrations.
"""

import asyncio
import time
import uuid
from collections.abc import Callable, Coroutine
from typing import Any, NamedTuple

import structlog

from app.schemas.jobs import JobState, JobStatusRead

logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────
JOB_BUD_CHAT = "bud_chat"
JOB_TRIAGE = "triage"
JOB_DESIGN_AGENT = "design_agent"
JOB_DESIGN_EXTRACT = "design_extract"
JOB_BUD_AGENT = "bud_agent"
JOB_TODO_GENERATE = "todo_generate"
JOB_JIRA_DISCOVERY = "jira_discovery"
JOB_JIRA_IMPORT = "jira_import"
JOB_JIRA_ENRICH = "jira_enrich"
JOB_SCAN = "scan"  # Future
JOB_AGENT_RUN = "agent_run"  # Future
JOB_PR_MERGE_UPDATE = "pr_merge_update"
JOB_REPO_BULK_ONBOARD = "repo_bulk_onboard"

_COMPLETED_TTL = 300  # seconds before cleanup
_QUEUE_MAXSIZE = 50  # backpressure limit per queue

# Sentinel value for "don't change" in partial updates. Using a unique object
# avoids ambiguity with legitimate ``None`` or other values that callers may
# want to assign.
_UNSET: Any = object()


class _JobEntry(NamedTuple):
    """Internal job store entry."""

    status: JobStatusRead
    created_mono: float
    user_id: str | None
    payload: dict[str, Any]


# ── Internal state ─────────────────────────────────────────────────
_job_store: dict[str, _JobEntry] = {}  # job_id → entry

# Live ``asyncio.Task`` for each in-flight handler. Populated by the
# worker when it starts running a job, removed when the handler
# returns. ``cancel_job`` uses this to actually interrupt the worker
# (via ``asyncio.Task.cancel``) rather than just flipping state bits.
_running_tasks: dict[str, asyncio.Task[None]] = {}

# Handler = async function(job_id: str, payload: dict) -> None
JobHandler = Callable[[str, dict[str, Any]], Coroutine[Any, Any, None]]

_registry: dict[str, tuple[JobHandler, int, asyncio.Queue[tuple[str, dict[str, Any]]]]] = {}
_workers: list[asyncio.Task[None]] = []

# Set once stop_workers() begins. Closes create_job() so jobs enqueued
# during the uvicorn-reload / shutdown window don't get accepted into
# queues that are about to be torn down.
_shutting_down: bool = False


# ── Public API ─────────────────────────────────────────────────────


def register_job_type(
    job_type: str,
    handler: JobHandler,
    *,
    worker_count: int = 1,
    queue_maxsize: int = _QUEUE_MAXSIZE,
) -> None:
    """Register a job type with its handler and worker count.

    Must be called before start_workers(). Any module can call this
    to add new job types without modifying this file.

    Args:
        job_type: Unique string identifier for the job type.
        handler: Async function(job_id, payload) that does the work.
        worker_count: Number of concurrent workers for this queue.
        queue_maxsize: Max pending jobs before backpressure (503).
    """
    queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue(maxsize=queue_maxsize)
    _registry[job_type] = (handler, worker_count, queue)
    logger.info("job_type_registered", job_type=job_type, workers=worker_count)


def create_job(
    job_type: str,
    *,
    payload: dict[str, Any],
    user_id: str | None = None,
) -> JobStatusRead:
    """Create a job and enqueue it for processing.

    Args:
        job_type: Registered job type string.
        payload: Job-specific data (validated by caller via Pydantic).
        user_id: Optional user ID for ownership tracking.

    Returns:
        JobStatusRead with initial QUEUED state.

    Raises:
        ValueError: If job_type is not registered.
        RuntimeError: If the app is shutting down.
        asyncio.QueueFull: If the queue has hit backpressure limit.
    """
    if _shutting_down:
        raise RuntimeError("Job queue is shutting down; not accepting new jobs")
    if job_type not in _registry:
        raise ValueError(f"Unknown job type: {job_type}")

    _, _, queue = _registry[job_type]
    job_id = str(uuid.uuid4())

    status = JobStatusRead(
        job_id=job_id,
        job_type=job_type,
        state=JobState.QUEUED,
        status_message="Queued",
    )
    _job_store[job_id] = _JobEntry(
        status=status,
        created_mono=time.monotonic(),
        user_id=user_id,
        payload=payload,
    )
    queue.put_nowait((job_id, payload))

    logger.info("job_created", job_id=job_id, job_type=job_type, user_id=user_id)
    return status


def get_job(job_id: str) -> JobStatusRead | None:
    """Look up a job's current status."""
    entry = _job_store.get(job_id)
    return entry.status if entry else None


def update_job(
    job_id: str,
    *,
    state: JobState | None = None,
    status_message: str | None = None,
    progress_pct: int | None = None,
    result: Any = _UNSET,  # sentinel: _UNSET means "don't change"
    error: str | None = _UNSET,
    error_code: str | None = _UNSET,
) -> None:
    """Update a job's status in-place.

    Only updates fields that are explicitly provided.

    Args:
        job_id: The job to update.
        state: New state (queued/running/completed/failed).
        status_message: Human-readable progress message.
        progress_pct: 0-100 progress percentage.
        result: Job result payload (only for completed jobs).
        error: Human-readable error message (only for failed jobs).
        error_code: Stable error category identifier for the frontend
            (e.g. "max_turns"); paired with ``error`` for failed jobs.
    """
    entry = _job_store.get(job_id)
    if entry is None:
        return
    job = entry.status
    if state is not None:
        job.state = state
    if status_message is not None:
        job.status_message = status_message
    if progress_pct is not None:
        job.progress_pct = progress_pct
    if result is not _UNSET:
        job.result = result
    if error is not _UNSET:
        job.error = error
    if error_code is not _UNSET:
        job.error_code = error_code

    # Push update over WebSocket event bus
    from app.services.event_bus import publish

    publish(f"job:{job_id}", job.model_dump(by_alias=True))

    # Create notification on terminal states for user-initiated jobs
    if state in (JobState.COMPLETED, JobState.FAILED) and entry.user_id:
        from app.services.notification_service import send_job_notification

        send_job_notification(
            job,
            user_id=entry.user_id,
            org_id=entry.payload.get("org_id") or "",
            payload=entry.payload,
        )


def cleanup_completed_jobs() -> int:
    """Remove completed/failed/cancelled jobs older than _COMPLETED_TTL.

    Returns:
        Number of jobs removed.
    """
    now = time.monotonic()
    terminal_states = (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED)
    stale = [
        jid
        for jid, entry in _job_store.items()
        if entry.status.state in terminal_states and entry.created_mono + _COMPLETED_TTL < now
    ]
    from app.services.event_bus import cleanup_topic

    for jid in stale:
        del _job_store[jid]
        cleanup_topic(f"job:{jid}")
    return len(stale)


def cancel_job(job_id: str, *, reason: str = "Cancelled by user") -> bool:
    """Signal an in-flight job to stop.

    Only the worker owns terminal state transitions on the job and the
    paired ``bud_agent_tasks`` row. This function's job is to poke the
    running ``asyncio.Task`` so the handler's ``CancelledError`` branch
    fires — the handler then cleans up (kills the Claude subprocess,
    marks the DB row FAILED with the supplied reason) and the worker
    emits the terminal WS event.

    If the job isn't tracked any more, or already terminal, no-op.
    Returns True when a live task was actually cancelled.
    """
    entry = _job_store.get(job_id)
    if entry is None:
        return False
    if entry.status.state in (JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED):
        return False

    # Stash the cancel reason so the worker's CancelledError branch can
    # use it as the error message on the terminal update.
    entry.status.status_message = reason

    task = _running_tasks.get(job_id)
    if task is None or task.done():
        # Either never started running, or finished right before we
        # reached here. Flip the state directly — no worker will touch
        # the row after this point.
        update_job(job_id, state=JobState.CANCELLED, error=reason)
        return True

    task.cancel()
    return True


def is_job_active(job_type: str, match_payload: dict[str, str]) -> bool:
    """Check if any active (queued/running) job of the given type matches the payload fields."""
    for entry in _job_store.values():
        if entry.status.job_type != job_type:
            continue
        if entry.status.state not in (JobState.QUEUED, JobState.RUNNING):
            continue
        if all(entry.payload.get(k) == v for k, v in match_payload.items()):
            return True
    return False


# ── Worker loop + lifecycle ────────────────────────────────────────


async def _worker(
    job_type: str,
    queue: asyncio.Queue[tuple[str, dict[str, Any]]],
    handler: JobHandler,
) -> None:
    """Generic worker loop: pull jobs, run handler, update status.

    Runs forever until cancelled. Catches all handler exceptions
    and marks the job as FAILED rather than crashing the worker.
    """
    while True:
        job_id, payload = await queue.get()
        try:
            update_job(job_id, state=JobState.RUNNING, status_message="Starting...")
            # Wrap the handler in an explicit Task so cancel_job can
            # interrupt it cleanly. Without this wrapping, cancelling
            # the worker's outer coroutine would kill the worker for
            # all subsequent jobs too.
            handler_task = asyncio.create_task(
                handler(job_id, payload),
                name=f"job-handler-{job_id}",
            )
            _running_tasks[job_id] = handler_task
            try:
                await handler_task
            finally:
                _running_tasks.pop(job_id, None)
        except asyncio.CancelledError:
            # Distinguish "this job was cancelled" from "the worker itself
            # is being cancelled" (shutdown). cancelling() > 0 means a
            # cancel is pending against *this* (outer worker) task — let
            # it propagate so stop_workers() can complete.
            current = asyncio.current_task()
            if current is not None and current.cancelling() > 0:
                raise
            # Otherwise: cancel_job(job_id) cancelled the inner handler.
            # The handler is responsible for its own DB/subprocess cleanup;
            # we just emit the terminal WS event and keep the worker alive.
            entry = _job_store.get(job_id)
            reason = (entry.status.status_message if entry else None) or "Cancelled by user"
            update_job(
                job_id,
                state=JobState.CANCELLED,
                error=reason,
                status_message="Cancelled",
            )
            logger.info("job_worker_cancelled", job_id=job_id, job_type=job_type)
        except Exception as exc:
            update_job(
                job_id,
                state=JobState.FAILED,
                error=str(exc)[:500],
                status_message="Failed",
            )
            logger.exception("job_worker_error", job_id=job_id, job_type=job_type)
        finally:
            queue.task_done()


async def start_workers() -> None:
    """Spawn worker tasks for all registered job types.

    Called from app lifespan after all job types are registered.
    """
    for job_type, (handler, worker_count, queue) in _registry.items():
        for i in range(worker_count):
            task = asyncio.create_task(
                _worker(job_type, queue, handler),
                name=f"job-worker-{job_type}-{i}",
            )
            _workers.append(task)
        logger.info("job_workers_started", job_type=job_type, count=worker_count)


async def stop_workers() -> None:
    """Cancel all worker tasks. Called from app lifespan shutdown."""
    global _shutting_down
    _shutting_down = True
    count = len(_workers)
    for task in _workers:
        task.cancel()
    await asyncio.gather(*_workers, return_exceptions=True)
    _workers.clear()
    logger.info("job_workers_stopped", count=count)
