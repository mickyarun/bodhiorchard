# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Step-level status transitions for v2 scan runs.

Pulled out of ``scan_run.py`` to keep that module focused on repo-run
CRUD; the four ``mark_step_*`` helpers all delegate to ``upsert_step``
with status-specific defaults. Co-located with ``scan_step_upsert.py``
which owns the ON-CONFLICT plumbing.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_phase import ScanPhase
from app.models.scan_repo_run import ScanRepoRun
from app.models.scan_repo_step import ScanRepoStep
from app.models.scan_run_enums import StepStatus
from app.repositories.scan_step_upsert import upsert_step


async def mark_step_running(
    db: AsyncSession,
    *,
    scan_repo_run_id: uuid.UUID,
    phase: ScanPhase,
) -> ScanRepoStep:
    """Insert or update a step row to RUNNING and stamp ``started_at``."""
    return await upsert_step(
        db,
        scan_repo_run_id=scan_repo_run_id,
        phase=phase,
        status=StepStatus.RUNNING,
        started_at=datetime.now(UTC),
    )


async def mark_step_done(
    db: AsyncSession,
    *,
    scan_repo_run_id: uuid.UUID,
    phase: ScanPhase,
    duration_ms: int,
    input_count: int = 0,
    kept_count: int = 0,
    dropped_count: int = 0,
    extras: dict[str, Any] | None = None,
) -> ScanRepoStep:
    """Stamp ``finished_at`` + counts on a successful phase completion."""
    return await upsert_step(
        db,
        scan_repo_run_id=scan_repo_run_id,
        phase=phase,
        status=StepStatus.DONE,
        finished_at=datetime.now(UTC),
        duration_ms=duration_ms,
        input_count=input_count,
        kept_count=kept_count,
        dropped_count=dropped_count,
        extras=extras or {},
    )


async def mark_step_failed(
    db: AsyncSession,
    *,
    scan_repo_run_id: uuid.UUID,
    phase: ScanPhase,
    error: str,
    duration_ms: int | None = None,
) -> ScanRepoStep:
    """Record a failed phase. Counts are intentionally not passed here so
    a prior DONE row's counts survive — see scan_step_upsert."""
    return await upsert_step(
        db,
        scan_repo_run_id=scan_repo_run_id,
        phase=phase,
        status=StepStatus.FAILED,
        finished_at=datetime.now(UTC),
        duration_ms=duration_ms,
        error=error[:2000],
    )


async def mark_step_skipped_cache(
    db: AsyncSession,
    *,
    scan_repo_run_id: uuid.UUID,
    phase: ScanPhase,
    extras: dict[str, Any] | None = None,
) -> ScanRepoStep:
    """Step skipped because a cached prior result was reused."""
    return await upsert_step(
        db,
        scan_repo_run_id=scan_repo_run_id,
        phase=phase,
        status=StepStatus.SKIPPED_CACHE,
        finished_at=datetime.now(UTC),
        extras=extras or {},
    )


async def find_steps_for_run(
    db: AsyncSession,
    *,
    scan_repo_run_id: uuid.UUID,
) -> list[ScanRepoStep]:
    """All step rows for one repo run, ordered by creation time."""
    stmt = (
        select(ScanRepoStep)
        .where(ScanRepoStep.scan_repo_run_id == scan_repo_run_id)
        .order_by(ScanRepoStep.created_at)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def find_latest_step_status_for_repo_phase(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    repo_id: uuid.UUID,
    phase: ScanPhase,
) -> StepStatus | None:
    """Return the status of the most recent step row for ``(repo, phase)``.

    Joins ``scan_repo_steps`` to ``scan_repo_runs`` so we can filter by org +
    repo across every prior scan, then takes the latest by ``created_at``.
    Used by the skip predicates to bypass the SHA cache when the prior
    attempt for this step ended in ``FAILED`` — re-running only the failed
    step instead of forcing a full rescan.

    Returns None when no step row has ever been recorded for this pairing.
    """
    stmt = (
        select(ScanRepoStep.status)
        .join(ScanRepoRun, ScanRepoRun.id == ScanRepoStep.scan_repo_run_id)
        .where(
            ScanRepoRun.org_id == org_id,
            ScanRepoRun.repo_id == repo_id,
            ScanRepoStep.phase == phase,
        )
        .order_by(ScanRepoStep.created_at.desc())
        .limit(1)
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def reset_steps_for_runs(
    db: AsyncSession,
    *,
    scan_repo_run_ids: list[uuid.UUID],
) -> int:
    """Reset every step row under the given runs back to QUEUED.

    Used by ``resume_v2_scan`` so the popover doesn't render skill counts
    or error messages from the failed prior attempt while the new walk
    is in flight. Idempotent — matches zero rows when there are no
    pre-existing steps.
    """
    if not scan_repo_run_ids:
        return 0
    result = await db.execute(
        sql_update(ScanRepoStep)
        .where(ScanRepoStep.scan_repo_run_id.in_(scan_repo_run_ids))
        .values(
            status=StepStatus.QUEUED.value,
            extras={},
            error=None,
            started_at=None,
            finished_at=None,
            duration_ms=None,
        )
    )
    return cast(CursorResult[Any], result).rowcount or 0
