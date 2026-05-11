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

"""DB-backed workflow observer.

Pulled out of ``observers.py`` so that file stays focused on the
Protocol + the no-op fallback. This module owns all the DB plumbing
for writing transitions into ``scan_repo_runs`` + ``scan_repo_steps``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy import update as sql_update

from app.models.scan import Scan
from app.models.scan_phase import ScanPhase
from app.scan.session import with_session

logger = structlog.get_logger(__name__)


class DBTimelineObserver:
    """Persists every workflow transition to ``scan_repo_runs`` + ``scan_repo_steps``.

    Each callback opens its own session via ``with_session`` so a stage
    that takes 20 minutes doesn't block a long-lived DB connection. The
    repo-run row must exist before ``on_run_start`` is called — the
    multi-repo scan runner upserts it as part of scan creation.
    """

    def __init__(
        self,
        *,
        org_id: uuid.UUID,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID,
    ) -> None:
        self.org_id = org_id
        self.scan_id = scan_id
        self.repo_id = repo_id

    async def on_run_start(self) -> None:
        try:
            async with with_session(self.org_id) as db:
                from app.repositories.scan_run import ScanRunRepository

                await ScanRunRepository(db, org_id=self.org_id).mark_repo_run_running(
                    scan_id=self.scan_id, repo_id=self.repo_id
                )
                await db.commit()
        except Exception:
            logger.exception("scan_observer_run_start_failed")

    async def on_step_running(self, *, phase: ScanPhase, input_count: int) -> None:
        await self._with_run(self._mark_step_running, phase=phase)

    async def on_step_done(
        self,
        *,
        phase: ScanPhase,
        input_count: int,
        kept_count: int,
        dropped_count: int,
        duration_ms: int,
        extras: dict[str, Any],
    ) -> None:
        await self._with_run(
            self._mark_step_done,
            phase=phase,
            input_count=input_count,
            kept_count=kept_count,
            dropped_count=dropped_count,
            duration_ms=duration_ms,
            extras=extras,
        )

    async def on_step_failed(self, *, phase: ScanPhase, error: str, duration_ms: int) -> None:
        await self._with_run(
            self._mark_step_failed,
            phase=phase,
            error=error,
            duration_ms=duration_ms,
        )

    async def on_step_skipped_cache(self, *, phase: ScanPhase, extras: dict[str, Any]) -> None:
        await self._with_run(self._mark_step_skipped_cache, phase=phase, extras=extras)

    async def on_run_done(self, *, feature_count: int | None = None) -> None:
        try:
            async with with_session(self.org_id) as db:
                from app.repositories.scan_run import ScanRunRepository

                run_repo = ScanRunRepository(db, org_id=self.org_id)
                await run_repo.mark_repo_run_done(
                    scan_id=self.scan_id,
                    repo_id=self.repo_id,
                    feature_count=feature_count,
                )
                # Mirror the run's terminal state onto ``tracked_repositories``
                # so ``_check_skip_unchanged`` can short-circuit the next
                # scan when the SHA hasn't moved. Without this, every
                # rescan re-runs extract/synthesize even though the repo
                # is unchanged — the column was being written by no one.
                await self._stamp_tracked_repo_completion(
                    db=db,
                    feature_count=feature_count,
                    run_repo=run_repo,
                )
                await db.commit()
        except Exception:
            logger.exception("scan_observer_run_done_failed")

    async def _stamp_tracked_repo_completion(
        self,
        *,
        db: Any,
        feature_count: int | None,
        run_repo: Any,
    ) -> None:
        """Copy the run's HEAD-at-start SHA + finished-at onto ``tracked_repositories``.

        Reads ``scan_repo_runs.head_sha_at_start`` (the SHA the run
        actually saw at start, captured in ``scan_setup``) and stamps it
        onto the tracked repo so the next scan's skip check has the data
        it needs. ``feature_count`` is mirrored when supplied; otherwise
        the existing column value is kept untouched.
        """
        from app.models.tracked_repository import TrackedRepository

        run = await run_repo._find_repo_run(  # noqa: SLF001
            scan_id=self.scan_id, repo_id=self.repo_id
        )
        if run is None:
            return
        tracked = await db.get(TrackedRepository, self.repo_id)
        if tracked is None:
            return
        if run.head_sha_at_start:
            tracked.head_sha = run.head_sha_at_start
        tracked.last_scanned_at = run.finished_at
        if feature_count is not None:
            tracked.feature_count = feature_count
        await db.flush()

    async def on_run_failed(self, *, error: str) -> None:
        try:
            async with with_session(self.org_id) as db:
                from app.repositories.scan_run import ScanRunRepository

                await ScanRunRepository(db, org_id=self.org_id).mark_repo_run_failed(
                    scan_id=self.scan_id, repo_id=self.repo_id, error=error
                )
                await db.commit()
        except Exception:
            logger.exception("scan_observer_run_failed_failed")

    # --- internals -----------------------------------------------------

    async def _with_run(self, fn: Any, *, phase: ScanPhase, **kwargs: Any) -> None:
        """Open a session, look up the repo run id, then dispatch to ``fn``.

        Wraps each callback so transient DB errors don't abort the
        pipeline body.
        """
        try:
            async with with_session(self.org_id) as db:
                from app.repositories.scan_run import ScanRunRepository

                repo_run_repo = ScanRunRepository(db, org_id=self.org_id)
                run = await repo_run_repo._find_repo_run(  # noqa: SLF001
                    scan_id=self.scan_id, repo_id=self.repo_id
                )
                if run is None:
                    logger.warning(
                        "scan_observer_run_missing",
                        scan_id=str(self.scan_id),
                        repo_id=str(self.repo_id),
                    )
                    return
                await fn(repo_run_repo, run.id, phase=phase, **kwargs)
                # Heartbeat the aggregate Scan row's ``updated_at`` so
                # ``ScanRepository.mark_stale_as_failed`` (2-hour cutoff)
                # never evicts an actively-progressing scan. V2 only
                # touches the aggregate row at start + terminal, so
                # without this any sufficiently long phase looks dead
                # to the staleness heuristic.
                await db.execute(
                    sql_update(Scan)
                    .where(Scan.id == self.scan_id, Scan.org_id == self.org_id)
                    .values(updated_at=datetime.now(UTC))
                )
                await db.commit()
        except Exception:
            logger.exception("scan_observer_step_failed", phase=str(phase))

    @staticmethod
    async def _mark_step_running(repo: Any, run_id: uuid.UUID, *, phase: ScanPhase) -> None:
        await repo.mark_step_running(scan_repo_run_id=run_id, phase=phase)

    @staticmethod
    async def _mark_step_done(
        repo: Any,
        run_id: uuid.UUID,
        *,
        phase: ScanPhase,
        input_count: int,
        kept_count: int,
        dropped_count: int,
        duration_ms: int,
        extras: dict[str, Any],
    ) -> None:
        await repo.mark_step_done(
            scan_repo_run_id=run_id,
            phase=phase,
            duration_ms=duration_ms,
            input_count=input_count,
            kept_count=kept_count,
            dropped_count=dropped_count,
            extras=extras,
        )

    @staticmethod
    async def _mark_step_failed(
        repo: Any,
        run_id: uuid.UUID,
        *,
        phase: ScanPhase,
        error: str,
        duration_ms: int,
    ) -> None:
        await repo.mark_step_failed(
            scan_repo_run_id=run_id,
            phase=phase,
            error=error,
            duration_ms=duration_ms,
        )

    @staticmethod
    async def _mark_step_skipped_cache(
        repo: Any,
        run_id: uuid.UUID,
        *,
        phase: ScanPhase,
        extras: dict[str, Any],
    ) -> None:
        await repo.mark_step_skipped_cache(scan_repo_run_id=run_id, phase=phase, extras=extras)
