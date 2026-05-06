# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Public lifecycle surface for the v2 scan pipeline.

Three entry points the API layer dispatches into:

* :func:`start_v2_scan` — POST /scans handler. Creates the Scan row,
  one ScanRepoRun per repo, kicks off the background fanout, returns
  the scan id immediately.
* :func:`resume_v2_scan` — POST /scans/{id}/resume handler. Looks at
  existing repo runs, retries the failed/incomplete ones.
* :func:`cancel_v2_scan` — POST /scans/{id}/cancel handler. Stops the
  in-flight task and flips any non-terminal repo runs to FAILED.

All three are no-throw at the orchestration layer: per-repo
exceptions land in the run's ``status=FAILED`` row, not a 500.
The background fanout body lives in ``runner_fanout.py``;
configuration helpers live in ``runner_config.py``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import structlog

from app.models.scan import ScanAggregateStatus
from app.models.scan_run_enums import RepoRunStatus
from app.repositories.scan import ScanRepository
from app.repositories.scan_run import ScanRunRepository
from app.scan.session import with_session
from app.schemas.scan import RunConfig
from app.services.scan.runner_fanout import (
    await_background_task,
    cancel_background_task,
    spawn_background_scan,
    wait_for_scan_task,
)
from app.services.scan.setup import (
    RepoDescriptor,
    create_scan_rows,
    load_repo_descriptor,
)

# Re-export so existing callers that imported from ``runner`` keep
# working without a churn-heavy rename across api/v1/scans.py and the
# scan_progress orphan reconciler.
__all__ = [
    "ScanAlreadyActiveError",
    "cancel_background_task",
    "cancel_v2_scan",
    "resume_v2_scan",
    "start_v2_scan",
    "wait_for_scan_task",
]

logger = structlog.get_logger(__name__)

# Wait at most this long for an in-flight scan task to finish its
# CancelledError handlers before we cascade-flip the DB rows. Five
# seconds covers a normal teardown without making the cancel endpoint
# block forever on a stuck task.
_CANCEL_AWAIT_TIMEOUT_SECONDS = 5.0


class ScanAlreadyActiveError(Exception):
    """Raised when an org tries to start a scan while another is in flight.

    Carries the in-flight ``scan_id`` so the API layer can return it in
    the 409 body — the frontend uses it to switch the timeline view to
    the running scan instead of starting a duplicate.
    """

    def __init__(self, scan_id: uuid.UUID, status: str) -> None:
        self.scan_id = scan_id
        self.status = status
        super().__init__(f"Scan {scan_id} is already active (status={status})")


async def start_v2_scan(
    *,
    org_id: uuid.UUID,
    repo_ids: list[uuid.UUID],
    config: RunConfig | None = None,
) -> uuid.UUID:
    """Create a v2 scan + per-repo runs, kick off the background fanout.

    Returns the new scan id immediately. Per-repo workflows run in
    parallel under ``gather_repos`` so they cooperatively share the
    asyncpg pool the same way the legacy scan does.
    """
    if not repo_ids:
        raise ValueError("repo_ids must be non-empty")

    # One scan at a time per org. Multi-repo within a single scan is
    # already parallel; allowing two concurrent scans would shadow each
    # other in the timeline UI (which only renders ``/scans/latest``).
    async with with_session(org_id) as db:
        existing = await ScanRepository(db, org_id=org_id).get_latest_active()
        if existing is not None:
            raise ScanAlreadyActiveError(scan_id=existing.id, status=existing.status)

    # ``RunConfig.stages`` defaults to the full v2 stage list
    # (``DEFAULT_PER_REPO_STAGES`` in ``app.schemas.scan``); callers that
    # want a subset pass ``config`` explicitly.
    config = config or RunConfig()
    scan_id, repo_descriptors = await create_scan_rows(
        org_id=org_id, repo_ids=repo_ids, full_rescan=config.full_rescan
    )

    spawn_background_scan(
        org_id=org_id, scan_id=scan_id, repo_descriptors=repo_descriptors, config=config
    )
    return scan_id


async def resume_v2_scan(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
    config: RunConfig | None = None,
) -> int:
    """Re-run any repos that aren't ``DONE`` or ``SKIPPED_UNCHANGED``.

    Returns the number of repo runs that were re-queued.
    """
    config = config or RunConfig()
    pending: list[RepoDescriptor] = []
    async with with_session(org_id) as db:
        scan = await ScanRepository(db, org_id=org_id).get(scan_id)
        if scan is None:
            raise LookupError(f"Scan {scan_id} not found for org {org_id}")
        run_repo = ScanRunRepository(db, org_id=org_id)
        runs = await run_repo.find_for_scan(scan_id=scan_id)
        resumed_run_ids: list[uuid.UUID] = []
        for run in runs:
            if run.status in {RepoRunStatus.DONE, RepoRunStatus.SKIPPED_UNCHANGED}:
                continue
            descriptor = await load_repo_descriptor(db, run.repo_id)
            if descriptor is None:
                continue
            run.status = RepoRunStatus.QUEUED
            run.started_at = None
            run.finished_at = None
            run.error = None
            resumed_run_ids.append(run.id)
            pending.append(descriptor)
        # Clear stale step state on resumed runs so the popover doesn't
        # render skill counts / errors from the failed prior attempt
        # until the new walk overwrites them.
        await run_repo.reset_steps_for_runs(scan_repo_run_ids=resumed_run_ids)
        scan.status = ScanAggregateStatus.STARTED.value
        scan.error = None
        await db.commit()

    if not pending:
        return 0

    spawn_background_scan(org_id=org_id, scan_id=scan_id, repo_descriptors=pending, config=config)
    return len(pending)


async def cancel_v2_scan(
    *,
    org_id: uuid.UUID,
    scan_id: uuid.UUID,
) -> bool:
    """Cancel an in-flight v2 scan: stop the task + flip subtree to FAILED.

    Returns True iff the Scan row exists and belonged to ``org_id``. The
    background task may already be done (e.g. a stuck scan after a
    backend restart); in that case there's nothing to await but we
    still cascade the DB update so the timeline doesn't stay
    perpetually RUNNING.

    Cancellation is a two-step handshake: first issue ``cancel()``,
    then ``await`` the task so its ``CancelledError`` handlers in
    ``workflow._execute_run`` finish writing per-step terminal rows
    BEFORE ``terminalize_subtree`` runs. Without this await, the two
    writers race on the same rows.
    """
    if cancel_background_task(scan_id):
        await await_background_task(scan_id, timeout=_CANCEL_AWAIT_TIMEOUT_SECONDS)

    async with with_session(org_id) as db:
        scan = await ScanRepository(db, org_id=org_id).get(scan_id)
        if scan is None:
            return False
        run_repo = ScanRunRepository(db, org_id=org_id)
        await run_repo.terminalize_subtree(
            scan_id=scan_id,
            error="Cancelled by user",
        )
        scan.status = ScanAggregateStatus.FAILED.value
        scan.error = "Cancelled by user"
        scan.updated_at = datetime.now(UTC)
        await db.commit()
    return True
