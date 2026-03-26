"""Async job queue with registry-based worker pools.

Provides a generic queue infrastructure that any service can register
job types with. Workers are spawned at startup based on registrations.
"""

import asyncio
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, NamedTuple

import structlog

from app.schemas.jobs import JobState, JobStatusRead

logger = structlog.get_logger(__name__)

# ── Constants ──────────────────────────────────────────────────────
JOB_BUD_CHAT = "bud_chat"
JOB_TRIAGE = "triage"
JOB_PRD_AGENT = "prd_agent"
JOB_DESIGN_AGENT = "design_agent"
JOB_DESIGN_EXTRACT = "design_extract"
JOB_TECH_ARCH = "tech_arch"
JOB_CODE_REVIEW = "code_review"
JOB_BUD_AGENT = "bud_agent"
JOB_SCAN = "scan"  # Future
JOB_AGENT_RUN = "agent_run"  # Future

_COMPLETED_TTL = 300  # seconds before cleanup
_QUEUE_MAXSIZE = 50  # backpressure limit per queue


class _JobEntry(NamedTuple):
    """Internal job store entry."""

    status: JobStatusRead
    created_mono: float
    user_id: str | None
    payload: dict[str, Any]


# ── Internal state ─────────────────────────────────────────────────
_job_store: dict[str, _JobEntry] = {}  # job_id → entry

# Handler = async function(job_id: str, payload: dict) -> None
JobHandler = Callable[[str, dict[str, Any]], Awaitable[None]]

_registry: dict[str, tuple[JobHandler, int, asyncio.Queue[tuple[str, dict[str, Any]]]]] = {}
_workers: list[asyncio.Task[None]] = []


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
        asyncio.QueueFull: If the queue has hit backpressure limit.
    """
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
    result: Any = ...,  # sentinel: ... means "don't change"
    error: str | None = ...,
) -> None:
    """Update a job's status in-place.

    Only updates fields that are explicitly provided.

    Args:
        job_id: The job to update.
        state: New state (queued/running/completed/failed).
        status_message: Human-readable progress message.
        progress_pct: 0-100 progress percentage.
        result: Job result payload (only for completed jobs).
        error: Error message (only for failed jobs).
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
    if result is not ...:
        job.result = result
    if error is not ...:
        job.error = error

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
    """Remove completed/failed jobs older than _COMPLETED_TTL.

    Returns:
        Number of jobs removed.
    """
    now = time.monotonic()
    stale = [
        jid
        for jid, entry in _job_store.items()
        if entry.status.state in (JobState.COMPLETED, JobState.FAILED)
        and entry.created_mono + _COMPLETED_TTL < now
    ]
    from app.services.event_bus import cleanup_topic

    for jid in stale:
        del _job_store[jid]
        cleanup_topic(f"job:{jid}")
    return len(stale)


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
            await handler(job_id, payload)
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
    count = len(_workers)
    for task in _workers:
        task.cancel()
    await asyncio.gather(*_workers, return_exceptions=True)
    _workers.clear()
    logger.info("job_workers_stopped", count=count)
