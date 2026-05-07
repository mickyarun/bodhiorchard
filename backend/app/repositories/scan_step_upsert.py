# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Idempotent upsert for ``scan_repo_steps`` rows.

Extracted from ``scan_run.py`` because the ON CONFLICT DO UPDATE
payload-shaping logic is the bulkiest single thing in that file. Keeping
it here lets ``scan_run.py`` stay under the file-size budget and lets us
unit-test the field-merge rules without touching the rest of the
repository.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan_phase import ScanPhase
from app.models.scan_repo_step import ScanRepoStep
from app.models.scan_run_enums import StepStatus


async def upsert_step(
    db: AsyncSession,
    *,
    scan_repo_run_id: uuid.UUID,
    phase: ScanPhase,
    status: StepStatus,
    started_at: datetime | None = None,
    finished_at: datetime | None = None,
    duration_ms: int | None = None,
    input_count: int | None = None,
    kept_count: int | None = None,
    dropped_count: int | None = None,
    extras: dict[str, Any] | None = None,
    error: str | None = None,
) -> ScanRepoStep:
    """Idempotent upsert keyed by ``(scan_repo_run_id, phase)``.

    Uses Postgres ON CONFLICT to merge fields without losing earlier
    state. Counts (``input_count`` / ``kept_count`` / ``dropped_count``)
    only update when the caller passes a real value: ``mark_step_failed``
    after a successful ``mark_step_done`` must not zero them.
    """
    insert_payload = _build_insert_payload(
        scan_repo_run_id=scan_repo_run_id,
        phase=phase,
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        input_count=input_count,
        kept_count=kept_count,
        dropped_count=dropped_count,
        extras=extras,
        error=error,
    )
    update_cols = _build_update_payload(
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        duration_ms=duration_ms,
        input_count=input_count,
        kept_count=kept_count,
        dropped_count=dropped_count,
        extras=extras,
        error=error,
    )
    stmt = (
        pg_insert(ScanRepoStep)
        .values(insert_payload)
        .on_conflict_do_update(
            index_elements=["scan_repo_run_id", "phase"],
            set_=update_cols,
        )
    )
    await db.execute(stmt)
    await db.flush()
    # Re-fetch so the caller gets a managed instance with all fields.
    result = await db.execute(
        select(ScanRepoStep).where(
            ScanRepoStep.scan_repo_run_id == scan_repo_run_id,
            ScanRepoStep.phase == phase,
        )
    )
    return result.scalar_one()


def _build_insert_payload(
    *,
    scan_repo_run_id: uuid.UUID,
    phase: ScanPhase,
    status: StepStatus,
    started_at: datetime | None,
    finished_at: datetime | None,
    duration_ms: int | None,
    input_count: int | None,
    kept_count: int | None,
    dropped_count: int | None,
    extras: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    """Initial INSERT shape; populates only the columns we have values for."""
    payload: dict[str, Any] = {
        "id": uuid.uuid4(),
        "scan_repo_run_id": scan_repo_run_id,
        "phase": phase.value,
        "status": status.value,
        # Counts default to 0 on INSERT (DB default is also 0); the
        # value-aware ON CONFLICT path is what protects against later
        # transitions clobbering them.
        "input_count": input_count or 0,
        "kept_count": kept_count or 0,
        "dropped_count": dropped_count or 0,
        "extras": extras or {},
    }
    if started_at is not None:
        payload["started_at"] = started_at
    if finished_at is not None:
        payload["finished_at"] = finished_at
    if duration_ms is not None:
        payload["duration_ms"] = duration_ms
    if error is not None:
        payload["error"] = error
    return payload


def _build_update_payload(
    *,
    status: StepStatus,
    started_at: datetime | None,
    finished_at: datetime | None,
    duration_ms: int | None,
    input_count: int | None,
    kept_count: int | None,
    dropped_count: int | None,
    extras: dict[str, Any] | None,
    error: str | None,
) -> dict[str, Any]:
    """ON CONFLICT update shape; only overwrites supplied fields.

    Counts update only when the caller passed a real (non-None) value.
    A later ``mark_step_failed`` after an earlier ``mark_step_done``
    must not zero the kept_count the DONE call wrote.
    """
    update_cols: dict[str, Any] = {"status": status.value}
    if input_count is not None:
        update_cols["input_count"] = input_count
    if kept_count is not None:
        update_cols["kept_count"] = kept_count
    if dropped_count is not None:
        update_cols["dropped_count"] = dropped_count
    if finished_at is not None:
        update_cols["finished_at"] = finished_at
    if duration_ms is not None:
        update_cols["duration_ms"] = duration_ms
    if extras is not None:
        update_cols["extras"] = extras
    if error is not None:
        update_cols["error"] = error
    # Only override started_at on the *transition* to RUNNING; later
    # status changes preserve the original start time.
    if started_at is not None and status == StepStatus.RUNNING:
        update_cols["started_at"] = started_at
    return update_cols
