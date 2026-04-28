# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""ScanPhaseCheckpoint data access repository.

All durable scan-resume state lives in ``scan_phase_checkpoints``. This
repo centralises the three read paths (within-scan lookup, cross-scan
SHA reuse, UI timeline listing) and the two write paths (start a new
RUNNING row, finalise it to DONE/FAILED/SKIPPED). ``run_checkpointed_phase``
(``app/services/scan_checkpoints.py``) is the only caller for writes.

Writes return primitive types (UUIDs / None) rather than ORM rows, so
the helper that owns the session can close it without leaving callers
holding detached instances. See ``BODHIORCHARD-ARCHITECTURE.md §18.12``.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Integer, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_phase import (
    TERMINAL_CHECKPOINT_STATUSES,
    CheckpointStatus,
    ScanPhase,
)
from app.models.scan_phase_checkpoint import ScanPhaseCheckpoint
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.repositories.base import BaseRepository


class ScanPhaseCheckpointRepository(BaseRepository[ScanPhaseCheckpoint]):
    """Repository for ``scan_phase_checkpoints`` rows, org-scoped.

    Attempts are monotonically increasing per ``(scan_id, repo_id, phase)``
    triple: the first run inserts attempt=1, a retry inserts attempt=2, etc.
    Most read paths want the *latest* attempt and therefore order by
    attempt DESC.
    """

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(ScanPhaseCheckpoint, db, org_id=org_id)

    async def list_active_repo_cluster_counts(
        self, scan_id: uuid.UUID, phase: ScanPhase
    ) -> list[tuple[uuid.UUID, str, int]]:
        """For each active repo with a checkpoint in this scan/phase,
        return (repo_id, repo_name, cluster_count) where ``cluster_count``
        is the integer ``feature_count`` from the checkpoint payload.

        Used by the end-of-scan audit to compare gitnexus cluster counts
        against the synth output.
        """
        stmt = self._scoped(
            select(
                ScanPhaseCheckpoint.repo_id,
                TrackedRepository.name,
                ScanPhaseCheckpoint.payload["feature_count"]
                .astext.cast(Integer)
                .label("cluster_count"),
            )
            .join(TrackedRepository, TrackedRepository.id == ScanPhaseCheckpoint.repo_id)
            .where(
                ScanPhaseCheckpoint.scan_id == scan_id,
                ScanPhaseCheckpoint.phase == phase,
                TrackedRepository.status == RepoStatus.ACTIVE,
            )
        )
        result = await self._db.execute(stmt)
        return [(row.repo_id, row.name, row.cluster_count) for row in result.all()]

    # --- Read paths -----------------------------------------------------

    async def get_latest(
        self,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        phase: ScanPhase,
    ) -> ScanPhaseCheckpoint | None:
        """Fetch the highest-attempt checkpoint for one (scan, repo, phase)."""
        stmt = self._scoped(
            select(ScanPhaseCheckpoint).where(
                ScanPhaseCheckpoint.scan_id == scan_id,
                ScanPhaseCheckpoint.phase == phase,
                self._repo_filter(repo_id),
            )
        ).order_by(ScanPhaseCheckpoint.attempt.desc())
        result = await self._db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def get_latest_scan_id(self) -> uuid.UUID | None:
        """Return the ``scan_id`` whose most recent checkpoint is newest for this org.

        Used by ``GET /scan/latest`` so the frontend can hydrate its
        "is there an active or recently-failed scan to render?" banner
        without relying on localStorage hints. Returns ``None`` if the
        org has never run a scan (no checkpoint rows exist), which the
        HTTP layer translates to ``204 No Content``.
        """
        stmt = (
            self._scoped(select(ScanPhaseCheckpoint))
            .order_by(ScanPhaseCheckpoint.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        row = result.scalar_one_or_none()
        return row.scan_id if row is not None else None

    async def list_for_scan(self, scan_id: uuid.UUID) -> list[ScanPhaseCheckpoint]:
        """List every checkpoint row for a scan, ordered for the UI timeline.

        Ordered by (created_at, phase) so per-repo rows cluster together
        and global phases appear after the per-repo stripe completes.
        """
        stmt = self._scoped(
            select(ScanPhaseCheckpoint).where(
                ScanPhaseCheckpoint.scan_id == scan_id,
            )
        ).order_by(
            ScanPhaseCheckpoint.created_at.asc(),
            ScanPhaseCheckpoint.phase.asc(),
            ScanPhaseCheckpoint.attempt.asc(),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def find_sha_reusable(
        self,
        repo_id: uuid.UUID,
        phase: ScanPhase,
        sha: str,
    ) -> ScanPhaseCheckpoint | None:
        """Find a DONE checkpoint with matching sha to reuse across scans.

        The org scope is inherited from the repository instance. Returns
        the most recent matching row (finished_at DESC).
        """
        stmt = self._scoped(
            select(ScanPhaseCheckpoint).where(
                ScanPhaseCheckpoint.repo_id == repo_id,
                ScanPhaseCheckpoint.phase == phase,
                ScanPhaseCheckpoint.sha_at_run == sha,
                ScanPhaseCheckpoint.status == CheckpointStatus.DONE,
            )
        ).order_by(ScanPhaseCheckpoint.finished_at.desc().nulls_last())
        result = await self._db.execute(stmt.limit(1))
        return result.scalar_one_or_none()

    async def next_attempt_number(
        self,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        phase: ScanPhase,
    ) -> int:
        """Return the next ``attempt`` to use for a (scan, repo, phase) row."""
        latest = await self.get_latest(scan_id, repo_id, phase)
        return (latest.attempt + 1) if latest is not None else 1

    # --- Write paths ----------------------------------------------------

    async def start(
        self,
        *,
        scan_id: uuid.UUID,
        repo_id: uuid.UUID | None,
        phase: ScanPhase,
        parent_scan_id: uuid.UUID | None = None,
        sha_at_run: str | None = None,
    ) -> uuid.UUID:
        """Insert a new RUNNING checkpoint and return its id.

        The caller cannot keep the ORM row because the dedicated
        checkpoint session may close before they finalise. The id is
        the durable handle they pass to ``finalize_by_id``.
        """
        attempt = await self.next_attempt_number(scan_id, repo_id, phase)
        assert self._org_id is not None, "org_id required for writes"
        now = datetime.now(UTC)
        row = ScanPhaseCheckpoint(
            scan_id=scan_id,
            parent_scan_id=parent_scan_id,
            org_id=self._org_id,
            repo_id=repo_id,
            phase=phase,
            status=CheckpointStatus.RUNNING,
            attempt=attempt,
            started_at=now,
            sha_at_run=sha_at_run,
            payload={},
        )
        self._db.add(row)
        await self._db.flush()
        return row.id

    async def finalize_by_id(
        self,
        checkpoint_id: uuid.UUID,
        *,
        status: CheckpointStatus,
        payload: dict[str, Any] | None = None,
        sha_at_run: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Flip a RUNNING checkpoint to a terminal status by primary key.

        One UPDATE statement, no load-modify-flush — so the call is
        safe inside a session that may not have the row in its identity
        map (e.g. a fresh ``_checkpoint_tx`` session that wasn't the
        one which inserted the RUNNING row).
        """
        if status not in TERMINAL_CHECKPOINT_STATUSES:
            raise ValueError(f"finalize_by_id() requires a terminal status, got {status!r}")
        assert self._org_id is not None, "org_id required for writes"
        values: dict[str, Any] = {
            "status": status,
            "finished_at": datetime.now(UTC),
            "error_code": error_code,
            "error_message": error_message,
        }
        if payload is not None:
            values["payload"] = payload
        if sha_at_run is not None:
            values["sha_at_run"] = sha_at_run
        await self._db.execute(
            sql_update(ScanPhaseCheckpoint)
            .where(
                ScanPhaseCheckpoint.id == checkpoint_id,
                ScanPhaseCheckpoint.org_id == self._org_id,
            )
            .values(**values)
        )

    async def insert_reused(
        self,
        *,
        scan_id: uuid.UUID,
        parent_scan_id: uuid.UUID | None,
        repo_id: uuid.UUID | None,
        phase: ScanPhase,
        payload: dict[str, Any],
        sha_at_run: str | None,
    ) -> uuid.UUID:
        """Insert a pre-completed DONE checkpoint that reuses prior work.

        Used by cross-scan SHA reuse: instead of running the phase, we
        copy the payload from an earlier DONE row and mark the new row
        DONE immediately with ``started_at == finished_at``. Returns the
        new id so callers stay symmetrical with ``start``.
        """
        assert self._org_id is not None, "org_id required for writes"
        attempt = await self.next_attempt_number(scan_id, repo_id, phase)
        now = datetime.now(UTC)
        row = ScanPhaseCheckpoint(
            scan_id=scan_id,
            parent_scan_id=parent_scan_id,
            org_id=self._org_id,
            repo_id=repo_id,
            phase=phase,
            status=CheckpointStatus.DONE,
            attempt=attempt,
            started_at=now,
            finished_at=now,
            sha_at_run=sha_at_run,
            payload=payload,
        )
        self._db.add(row)
        await self._db.flush()
        return row.id

    async def copy_terminal_from_parent(
        self,
        *,
        parent_scan_id: uuid.UUID,
        new_scan_id: uuid.UUID,
        exclude_phase: ScanPhase | None = None,
        exclude_repo_id: uuid.UUID | None = None,
    ) -> int:
        """Copy DONE and SKIPPED checkpoints from parent to child scan.

        Called when the user hits /resume. The child scan inherits the
        parent's successful work; phases that were FAILED / PENDING /
        RUNNING in the parent are NOT copied — they will be re-executed
        by ``run_scan_pipeline`` under the new ``scan_id``.

        ``exclude_phase`` / ``exclude_repo_id`` support the /retry
        endpoint: a specific phase checkpoint the user wants to re-run
        is deliberately *not* forwarded, so the child scan will run it
        fresh. When ``exclude_repo_id`` is ``None`` for a per-repo
        phase, every repo's checkpoint for that phase is excluded
        (useful for global-phase retries).

        Returns:
            Number of rows copied.
        """
        assert self._org_id is not None, "org_id required for writes"
        parent_rows = await self._db.execute(
            self._scoped(
                select(ScanPhaseCheckpoint).where(
                    ScanPhaseCheckpoint.scan_id == parent_scan_id,
                    ScanPhaseCheckpoint.status.in_(
                        (CheckpointStatus.DONE, CheckpointStatus.SKIPPED)
                    ),
                )
            )
        )
        copied = 0
        for src in parent_rows.scalars().all():
            # Per-repo-phase retry: skip the one specific (phase, repo_id).
            # Global-phase retry (repo_id=None): skip every row for that phase.
            if (
                exclude_phase is not None
                and src.phase is exclude_phase
                and (exclude_repo_id is None or src.repo_id == exclude_repo_id)
            ):
                continue
            self._db.add(
                ScanPhaseCheckpoint(
                    scan_id=new_scan_id,
                    parent_scan_id=parent_scan_id,
                    org_id=self._org_id,
                    repo_id=src.repo_id,
                    phase=src.phase,
                    status=src.status,
                    attempt=1,
                    started_at=src.started_at,
                    finished_at=src.finished_at,
                    sha_at_run=src.sha_at_run,
                    payload=src.payload,
                )
            )
            copied += 1
        if copied:
            await self._db.flush()
        return copied

    # --- Helpers --------------------------------------------------------

    @staticmethod
    def _repo_filter(repo_id: uuid.UUID | None) -> Any:
        """Build a WHERE clause for repo_id handling the NULL (GLOBAL) case.

        Global phases store ``repo_id = NULL`` so we must use IS NULL rather
        than ``= NULL`` (which never matches) to find them.
        """
        if repo_id is None:
            return ScanPhaseCheckpoint.repo_id.is_(None)
        return ScanPhaseCheckpoint.repo_id == repo_id
