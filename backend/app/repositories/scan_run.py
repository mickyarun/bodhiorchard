# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Repository for ``scan_repo_runs`` and ``scan_repo_steps``.

Used by the scan workflow to:
* create one ``ScanRepoRun`` per (scan, repo) at scan start
* upsert a ``ScanRepoStep`` row at every status transition
* publish event-bus updates for the timeline UI
* find the resume point for a scan that was interrupted

All access is org-scoped.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, cast

import structlog
from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_phase import ScanPhase
from app.models.scan_repo_run import ScanRepoRun
from app.models.scan_repo_step import ScanRepoStep
from app.models.scan_run_enums import RepoRunStatus, StepStatus
from app.models.tracked_repository import TrackedRepository
from app.repositories.scan_step_status import (
    find_steps_for_run,
    mark_step_done,
    mark_step_failed,
    mark_step_running,
    mark_step_skipped_cache,
    reset_steps_for_runs,
)

logger = structlog.get_logger(__name__)


class ScanRunRepository:
    """Org-scoped CRUD over ``scan_repo_runs`` and ``scan_repo_steps``."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self.db = db
        self.org_id = org_id

    # --- repo runs ----------------------------------------------------

    async def upsert_repo_run(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID,
        head_sha_at_start: str | None,
    ) -> ScanRepoRun:
        """Create or fetch the (scan, repo) run row at scan start."""
        existing = await self._find_repo_run(scan_id=scan_id, repo_id=repo_id)
        if existing is not None:
            return existing
        row = ScanRepoRun(
            org_id=self.org_id,
            scan_id=scan_id,
            repo_id=repo_id,
            head_sha_at_start=head_sha_at_start,
            status=RepoRunStatus.QUEUED,
        )
        self.db.add(row)
        await self.db.flush()
        return row

    async def mark_repo_run_running(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID,
    ) -> None:
        run = await self._find_repo_run(scan_id=scan_id, repo_id=repo_id)
        if run is None:
            return
        run.status = RepoRunStatus.RUNNING
        run.started_at = datetime.now(UTC)
        await self.db.flush()

    async def mark_repo_run_done(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID,
        feature_count: int | None = None,
        skill_count: int | None = None,
    ) -> None:
        run = await self._find_repo_run(scan_id=scan_id, repo_id=repo_id)
        if run is None:
            return
        run.status = RepoRunStatus.DONE
        run.finished_at = datetime.now(UTC)
        if feature_count is not None:
            run.feature_count = feature_count
        if skill_count is not None:
            run.skill_count = skill_count
        await self.db.flush()

    async def mark_repo_run_failed(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID,
        error: str,
    ) -> None:
        run = await self._find_repo_run(scan_id=scan_id, repo_id=repo_id)
        if run is None:
            return
        run.status = RepoRunStatus.FAILED
        run.finished_at = datetime.now(UTC)
        run.error = error[:2000]
        await self.db.flush()

    async def mark_repo_run_skipped_unchanged(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID,
    ) -> None:
        """Cache hit: HEAD SHA matches a prior successful run for this repo."""
        run = await self._find_repo_run(scan_id=scan_id, repo_id=repo_id)
        if run is None:
            return
        run.status = RepoRunStatus.SKIPPED_UNCHANGED
        run.finished_at = datetime.now(UTC)
        await self.db.flush()

    async def find_for_scan(self, *, scan_id: uuid.UUID) -> list[ScanRepoRun]:
        """All repo runs for one scan, oldest first."""
        stmt = (
            select(ScanRepoRun)
            .where(
                ScanRepoRun.org_id == self.org_id,
                ScanRepoRun.scan_id == scan_id,
            )
            .order_by(ScanRepoRun.created_at)
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def list_repo_paths_for_scan(self, *, scan_id: uuid.UUID) -> list[str]:
        """Tracked-repo paths registered against this scan.

        Joins ``scan_repo_runs`` to ``tracked_repositories`` so the
        global-phases caller gets one round-trip instead of N+1.
        """
        stmt = (
            select(TrackedRepository.path)
            .join(ScanRepoRun, ScanRepoRun.repo_id == TrackedRepository.id)
            .where(
                ScanRepoRun.scan_id == scan_id,
                ScanRepoRun.org_id == self.org_id,
            )
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def find_latest_per_repo(
        self,
        *,
        repo_ids: list[uuid.UUID] | None = None,
    ) -> dict[uuid.UUID, ScanRepoRun]:
        """Latest run per repo across all scans, scoped to this org.

        Single ``DISTINCT ON`` query — picks the row with the most recent
        ``finished_at`` (NULLS LAST so an in-flight RUNNING row beats an
        older DONE row only after it completes; while running, the prior
        completed row still wins so the card keeps showing the last
        successful summary).

        Used by the Settings → Code list to stamp every row with its
        last-scan recency + status, regardless of which scan produced it.
        """
        if repo_ids is not None and not repo_ids:
            return {}
        stmt = (
            select(ScanRepoRun)
            .where(ScanRepoRun.org_id == self.org_id)
            .distinct(ScanRepoRun.repo_id)
            .order_by(
                ScanRepoRun.repo_id,
                ScanRepoRun.finished_at.desc().nulls_last(),
                ScanRepoRun.started_at.desc().nulls_last(),
                ScanRepoRun.created_at.desc(),
            )
        )
        if repo_ids is not None:
            stmt = stmt.where(ScanRepoRun.repo_id.in_(repo_ids))
        result = await self.db.execute(stmt)
        return {row.repo_id: row for row in result.scalars().all()}

    # --- steps (delegate to scan_step_status helpers) -----------------

    async def mark_step_running(
        self, *, scan_repo_run_id: uuid.UUID, phase: ScanPhase
    ) -> ScanRepoStep:
        return await mark_step_running(self.db, scan_repo_run_id=scan_repo_run_id, phase=phase)

    async def mark_step_done(
        self,
        *,
        scan_repo_run_id: uuid.UUID,
        phase: ScanPhase,
        duration_ms: int,
        input_count: int = 0,
        kept_count: int = 0,
        dropped_count: int = 0,
        extras: dict[str, Any] | None = None,
    ) -> ScanRepoStep:
        return await mark_step_done(
            self.db,
            scan_repo_run_id=scan_repo_run_id,
            phase=phase,
            duration_ms=duration_ms,
            input_count=input_count,
            kept_count=kept_count,
            dropped_count=dropped_count,
            extras=extras,
        )

    async def mark_step_failed(
        self,
        *,
        scan_repo_run_id: uuid.UUID,
        phase: ScanPhase,
        error: str,
        duration_ms: int | None = None,
    ) -> ScanRepoStep:
        return await mark_step_failed(
            self.db,
            scan_repo_run_id=scan_repo_run_id,
            phase=phase,
            error=error,
            duration_ms=duration_ms,
        )

    async def mark_step_skipped_cache(
        self,
        *,
        scan_repo_run_id: uuid.UUID,
        phase: ScanPhase,
        extras: dict[str, Any] | None = None,
    ) -> ScanRepoStep:
        return await mark_step_skipped_cache(
            self.db,
            scan_repo_run_id=scan_repo_run_id,
            phase=phase,
            extras=extras,
        )

    async def find_steps_for_run(self, *, scan_repo_run_id: uuid.UUID) -> list[ScanRepoStep]:
        return await find_steps_for_run(self.db, scan_repo_run_id=scan_repo_run_id)

    async def find_steps_grouped_by_run(
        self, *, run_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, list[ScanRepoStep]]:
        """Fetch all steps for these runs in one round-trip, grouped by run id.

        Used by serializers that render multi-repo scan timelines so the
        N runs don't fan out into N step-lookups. Joined to
        ``ScanRepoRun`` so the org_id filter applies even when callers
        pass run_ids from sources other than ``find_for_scan``.
        """
        if not run_ids:
            return {}
        stmt = (
            select(ScanRepoStep)
            .join(ScanRepoRun, ScanRepoRun.id == ScanRepoStep.scan_repo_run_id)
            .where(
                ScanRepoStep.scan_repo_run_id.in_(run_ids),
                ScanRepoRun.org_id == self.org_id,
            )
            .order_by(ScanRepoStep.created_at)
        )
        grouped: dict[uuid.UUID, list[ScanRepoStep]] = {rid: [] for rid in run_ids}
        for step in (await self.db.execute(stmt)).scalars().all():
            grouped[step.scan_repo_run_id].append(step)
        return grouped

    async def reset_steps_for_runs(self, *, scan_repo_run_ids: list[uuid.UUID]) -> int:
        return await reset_steps_for_runs(self.db, scan_repo_run_ids=scan_repo_run_ids)

    async def terminalize_subtree(
        self,
        *,
        scan_id: uuid.UUID,
        error: str,
    ) -> tuple[int, int]:
        """Force every non-terminal repo run + step under one scan to FAILED.

        Used by both the cancel endpoint and the startup orphan reconciler
        so a stuck or interrupted scan doesn't leave the per-repo timeline
        in a perpetual RUNNING state. Idempotent — already-terminal rows
        are not touched.

        Returns ``(runs_flipped, steps_flipped)``.
        """
        truncated = error[:2000]
        now = datetime.now(UTC)
        run_result = await self.db.execute(
            sql_update(ScanRepoRun)
            .where(
                ScanRepoRun.org_id == self.org_id,
                ScanRepoRun.scan_id == scan_id,
                ScanRepoRun.status.in_([RepoRunStatus.QUEUED.value, RepoRunStatus.RUNNING.value]),
            )
            .values(
                status=RepoRunStatus.FAILED.value,
                finished_at=now,
                error=truncated,
            )
            .returning(ScanRepoRun.id)
        )
        run_ids = list(run_result.scalars().all())
        runs_flipped = len(run_ids)

        steps_flipped = 0
        if run_ids:
            step_result = await self.db.execute(
                sql_update(ScanRepoStep)
                .where(
                    ScanRepoStep.scan_repo_run_id.in_(run_ids),
                    ScanRepoStep.status == StepStatus.RUNNING.value,
                )
                .values(
                    status=StepStatus.FAILED.value,
                    finished_at=now,
                    error=truncated,
                )
            )
            steps_flipped = cast(CursorResult[Any], step_result).rowcount or 0

        logger.info(
            "scan_subtree_terminalized",
            scan_id=str(scan_id),
            runs_flipped=runs_flipped,
            steps_flipped=steps_flipped,
        )
        return runs_flipped, steps_flipped

    # --- internals ----------------------------------------------------

    async def _find_repo_run(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID,
    ) -> ScanRepoRun | None:
        stmt = select(ScanRepoRun).where(
            ScanRepoRun.org_id == self.org_id,
            ScanRepoRun.scan_id == scan_id,
            ScanRepoRun.repo_id == repo_id,
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()
