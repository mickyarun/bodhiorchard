# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Scan progress tracking backed by the ``scans`` table.

Single source of truth for scan lifecycle + aggregate progress. Each
public function opens its own short-lived ``AsyncSessionLocal`` so the
long-running background scan task doesn't have to thread a session
through every progress-update call site.

Every write publishes the updated ``ScanStatus`` to the event bus for
WebSocket delivery (deduplicated via ``publish_scan_status``). The
per-phase timeline lives in ``scan_phase_checkpoints``; callers that
need it call ``enrich_status_with_phases`` on top of what this module
returns.
"""

from __future__ import annotations

import asyncio as _asyncio
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan import Scan
from app.repositories.scan import ScanRepository
from app.schemas.skills import PhaseStatus, ScanStatus, phase_label
from app.services.event_bus import publish

logger = structlog.get_logger(__name__)


# ── Internal helpers ────────────────────────────────────────────────


def _scan_to_status(row: Scan) -> ScanStatus:
    """Translate a DB row to the outward-facing ``ScanStatus`` schema.

    Defensive against partially-hydrated instances: SQLAlchemy's
    ``default=`` on ``mapped_column`` only fires at INSERT time, so a
    unit test constructing ``Scan(id=..., org_id=...)`` leaves the
    non-nullable fields at Python-None until the row lands in the DB.
    We coalesce to the same defaults the DB would supply so every
    code path sees a consistent shape.
    """
    return ScanStatus(
        scan_id=str(row.id),
        status=row.status or "started",
        scan_mode=row.scan_mode or "full",
        progress_pct=row.progress_pct or 0,
        features_indexed=row.features_indexed or 0,
        features_skipped=row.features_skipped or 0,
        profiles_found=row.profiles_found or 0,
        stale_cleaned=row.stale_cleaned or 0,
        unmatched_authors=list(row.unmatched_authors or []),
        synthesis_warning=row.synthesis_warning,
        setup_pr_message=row.setup_pr_message,
        repo_warnings=list(row.repo_warnings or []),
        parent_scan_id=str(row.parent_scan_id) if row.parent_scan_id else None,
        error=row.error,
    )


def _publish(scan_id: str, status: ScanStatus) -> None:
    """Publish to ``scan:{scan_id}`` with digest-dedup, best-effort.

    No running loop (some tests) or malformed UUID ⇒ fall through to
    the raw ``publish`` so existing test suites keep receiving events.
    """
    payload = status.model_dump(by_alias=True)
    topic = f"scan:{scan_id}"

    try:
        scan_uuid = uuid.UUID(scan_id)
    except (ValueError, TypeError):
        publish(topic, payload)
        return

    try:
        loop = _asyncio.get_running_loop()
    except RuntimeError:
        publish(topic, payload)
        return

    from app.services.scan_checkpoints import publish_scan_status as _publish_dedup

    loop.create_task(_publish_dedup(scan_uuid, payload))


# ── Public API ──────────────────────────────────────────────────────


async def create_scan_progress(
    scan_id: str,
    org_id: str,
    *,
    parent_scan_id: str | None = None,
) -> ScanStatus:
    """Insert a fresh ``scans`` row at ``status='started'``, progress 0.

    Called once at the top of ``run_scan_pipeline`` (and by the
    resume / retry / reset endpoints). Idempotent: if a row already
    exists for this ``scan_id`` we return its current state so
    retries don't blow up on the PK conflict.
    """
    from app.database import AsyncSessionLocal

    scan_uuid = uuid.UUID(scan_id)
    org_uuid = uuid.UUID(org_id)
    parent_uuid = uuid.UUID(parent_scan_id) if parent_scan_id else None

    async with AsyncSessionLocal() as db:
        repo = ScanRepository(db, org_id=org_uuid)
        existing = await repo.get(scan_uuid)
        if existing is not None:
            status = _scan_to_status(existing)
        else:
            row = await repo.create_initial(scan_uuid, parent_scan_id=parent_uuid)
            await db.commit()
            status = _scan_to_status(row)

    _publish(scan_id, status)
    return status


async def update_scan_progress(
    scan_id: str,
    *,
    status: str | None = None,
    progress_pct: int | None = None,
    **fields: object,
) -> ScanStatus | None:
    """Partial update — monotonic progress, optional status, arbitrary fields.

    Fields mirror the ``ScanStatus`` schema. Callers can pass any
    subset; omitted fields keep their current value. Returns the
    updated ``ScanStatus`` or ``None`` if the scan no longer exists.
    """
    from app.database import AsyncSessionLocal

    try:
        scan_uuid = uuid.UUID(scan_id)
    except (ValueError, TypeError):
        return None

    # Extract known-typed updates; anything else is passed through
    # as-is so a future new column doesn't require a touch here.
    from typing import Any

    typed: dict[str, Any] = {}
    for key, value in fields.items():
        if value is not None:
            typed[key] = value
    if status is not None:
        typed["status"] = status

    async with AsyncSessionLocal() as db:
        # The repo's apply_update method needs org_id scoping — but we
        # don't know the org from scan_id alone without a first lookup.
        # Do that lookup unscoped (PK access), then write scoped.
        preload = await db.get(Scan, scan_uuid)
        if preload is None:
            return None

        repo = ScanRepository(db, org_id=preload.org_id)
        row = await repo.apply_update(
            scan_uuid,
            clamp_progress_to=progress_pct,
            **typed,
        )
        await db.commit()
        if row is None:
            return None
        out = _scan_to_status(row)

    _publish(scan_id, out)
    return out


async def append_repo_warning(
    scan_id: str,
    *,
    repo: str,
    phase: str,
    summary: str,
    hint: str | None = None,
) -> ScanStatus | None:
    """Append one warning dict to the scan's ``repo_warnings`` JSONB array.

    Uses a single atomic ``UPDATE ... SET repo_warnings = repo_warnings
    || $1`` so two concurrent synthesis workers can both land warnings
    without one overwriting the other.
    """
    from app.database import AsyncSessionLocal

    try:
        scan_uuid = uuid.UUID(scan_id)
    except (ValueError, TypeError):
        return None

    warning: dict[str, object] = {"repo": repo, "phase": phase, "summary": summary}
    if hint is not None:
        warning["hint"] = hint

    async with AsyncSessionLocal() as db:
        preload = await db.get(Scan, scan_uuid)
        if preload is None:
            return None
        repo_db = ScanRepository(db, org_id=preload.org_id)
        row = await repo_db.apply_update(
            scan_uuid,
            append_repo_warning=warning,
        )
        await db.commit()
        if row is None:
            return None
        out = _scan_to_status(row)

    _publish(scan_id, out)
    return out


async def get_scan_progress(scan_id: str) -> ScanStatus | None:
    """Look up a scan by id. Triggers lazy stale-to-failed eviction on read."""
    from app.database import AsyncSessionLocal

    try:
        scan_uuid = uuid.UUID(scan_id)
    except (ValueError, TypeError):
        return None

    async with AsyncSessionLocal() as db:
        row = await db.get(Scan, scan_uuid)
        if row is None:
            return None
        repo = ScanRepository(db, org_id=row.org_id)
        stale = await repo.mark_stale_as_failed(scan_uuid)
        if stale is not None:
            await db.commit()
            return _scan_to_status(stale)
        return _scan_to_status(row)


async def resolve_scan_progress(scan_id: str, org_id: str) -> ScanStatus | None:
    """Prefer the direct id hit; fall back to the org's active scan.

    Matches the old Redis behaviour — a poll that lands between a scan
    ending and a new one starting would still get a stable answer
    instead of a phantom 404.
    """
    direct = await get_scan_progress(scan_id)
    if direct is not None:
        return direct
    return await get_active_scan_for_org(org_id)


async def get_active_scan_for_org(org_id: str) -> ScanStatus | None:
    """Return the org's most-recently-updated non-terminal scan."""
    from app.database import AsyncSessionLocal

    try:
        org_uuid = uuid.UUID(org_id)
    except (ValueError, TypeError):
        return None

    async with AsyncSessionLocal() as db:
        repo = ScanRepository(db, org_id=org_uuid)
        row = await repo.get_latest_active()
        if row is None:
            return None
        # Opportunistically evict if this "active" row has gone stale.
        stale = await repo.mark_stale_as_failed(row.id)
        if stale is not None:
            await db.commit()
            return None
        return _scan_to_status(row)


async def cancel_scan(scan_id: str) -> ScanStatus | None:
    """Explicit cancel — flip to ``failed`` with a human-readable error."""
    return await update_scan_progress(
        scan_id,
        status="failed",
        error="Scan cancelled by request.",
    )


async def reconcile_orphan_scans(*, min_age_seconds: int = 60) -> int:
    """Mark active scans with no running task as failed.

    Called once at app startup. When the backend restarts mid-scan,
    the ``run_scan_pipeline`` coroutine is torn down without running
    its ``except`` block, so the ``scans`` row keeps its last
    non-terminal status forever — the frontend sees the zombie scan,
    polls it indefinitely, and users can't start a new one because
    ``get_active_scan_for_org`` returns the zombie.

    ``min_age_seconds`` gates the sweep so we never flip a scan that
    was dispatched seconds ago by another still-living worker. In
    single-process deployments (the common case) this is safe with a
    small window: a freshly-restarted process has no running scan
    tasks by definition. In multi-worker deployments, overlapping
    startups would all see the same active rows; the first to commit
    wins, the others' UPDATEs match zero rows and no-op.

    Returns:
        Count of rows flipped to ``failed``.
    """
    from datetime import timedelta

    from sqlalchemy import select
    from sqlalchemy import update as sql_update

    from app.database import AsyncSessionLocal
    from app.repositories.scan import _active_status_values  # noqa: PLC2701

    cutoff = datetime.now(UTC) - timedelta(seconds=min_age_seconds)
    error_msg = (
        "Scan interrupted by backend restart. Use Resume from the "
        "Settings → Code Index panel to pick up where it left off."
    )

    async with AsyncSessionLocal() as db:
        result = await db.execute(
            sql_update(Scan)
            .where(
                Scan.status.in_(_active_status_values()),
                Scan.updated_at < cutoff,
            )
            .values(
                status="failed",
                error=error_msg,
                updated_at=datetime.now(UTC),
            )
            .returning(Scan.id)
        )
        orphan_ids = list(result.scalars().all())
        if orphan_ids:
            await db.commit()
            logger.warning(
                "scan_orphans_reconciled",
                count=len(orphan_ids),
                scan_ids=[str(s) for s in orphan_ids],
            )
            # Also push a final "failed" WS event so any already-open
            # browser tab flips out of its polling loop immediately
            # instead of waiting for its next /scan/latest poll.
            for scan_id in orphan_ids:
                select_stmt = select(Scan).where(Scan.id == scan_id)
                row = (await db.execute(select_stmt)).scalar_one_or_none()
                if row is not None:
                    _publish(str(scan_id), _scan_to_status(row))
        return len(orphan_ids)


async def enrich_status_with_phases(
    db: AsyncSession,
    org_id: uuid.UUID,
    status: ScanStatus,
) -> ScanStatus:
    """Attach ``phases[]`` + ``parent_scan_id`` to a ``ScanStatus`` row.

    Called from HTTP handlers that serve poll-based status reads so the
    frontend timeline has authoritative per-phase data. Uses the
    caller's request-scoped session so we don't open a second one just
    for the join.
    """
    from sqlalchemy import select as _select

    from app.models.scan_phase import PHASE_SCOPE, ScanPhase
    from app.models.tracked_repository import TrackedRepository
    from app.repositories.scan_phase_checkpoint import ScanPhaseCheckpointRepository

    try:
        scan_uuid = uuid.UUID(status.scan_id)
    except (ValueError, TypeError):
        return status

    ck_repo = ScanPhaseCheckpointRepository(db, org_id=org_id)
    rows = await ck_repo.list_for_scan(scan_uuid)
    if not rows:
        return status

    repo_ids = {row.repo_id for row in rows if row.repo_id is not None}
    repo_names: dict[uuid.UUID, str] = {}
    if repo_ids:
        name_rows = await db.execute(
            _select(TrackedRepository.id, TrackedRepository.name).where(
                TrackedRepository.id.in_(repo_ids),
            )
        )
        repo_names = {rid: rname for rid, rname in name_rows.all()}

    phases: list[PhaseStatus] = []
    parent_id: str | None = status.parent_scan_id
    for row in rows:
        if parent_id is None and row.parent_scan_id is not None:
            parent_id = str(row.parent_scan_id)
        phase_value = row.phase.value if hasattr(row.phase, "value") else str(row.phase)
        phase_enum = ScanPhase(phase_value)
        sha_reused = (
            row.started_at is not None
            and row.finished_at is not None
            and row.started_at == row.finished_at
        )
        phases.append(
            PhaseStatus(
                phase=phase_value,
                phase_label=phase_label(phase_value),
                scope=PHASE_SCOPE[phase_enum].value,
                repo_id=str(row.repo_id) if row.repo_id else None,
                repo_name=repo_names.get(row.repo_id) if row.repo_id else None,
                status=row.status.value if hasattr(row.status, "value") else str(row.status),
                attempt=row.attempt,
                error_code=row.error_code,
                error_message=row.error_message,
                started_at=row.started_at.isoformat() if row.started_at else None,
                finished_at=row.finished_at.isoformat() if row.finished_at else None,
                sha_reused=sha_reused,
            )
        )

    return status.model_copy(update={"phases": phases, "parent_scan_id": parent_id})
