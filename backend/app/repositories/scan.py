# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Scan data-access repository.

Every ``scan_progress.*`` public function routes reads/writes through
this repo. Keeps the SQL shape in one place and makes
``scan_progress.py`` a thin façade that callers keep using with no
signature change — the Redis → Postgres migration is invisible above
this layer.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import bindparam, func, select
from sqlalchemy import update as sql_update
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.scan import ACTIVE_SCAN_STATUSES, Scan
from app.repositories.base import BaseRepository

# Scans older than this with no updates get flipped to ``failed`` on
# the next read. Must exceed the longest legitimate silence between
# progress updates (Claude synthesis can idle for several minutes).
# Matches the old Redis TTL so operators don't have to relearn the
# stale window when we remove Redis.
STALE_TIMEOUT = timedelta(hours=2)


class ScanRepository(BaseRepository[Scan]):
    """Repository for the ``scans`` table, org-scoped."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(Scan, db, org_id=org_id)

    async def create_initial(
        self,
        scan_id: uuid.UUID,
        *,
        parent_scan_id: uuid.UUID | None = None,
    ) -> Scan:
        """Insert a fresh scan row at ``status='started'`` progress 0."""
        assert self._org_id is not None, "org_id required"
        row = Scan(
            id=scan_id,
            org_id=self._org_id,
            parent_scan_id=parent_scan_id,
            status="started",
        )
        self._db.add(row)
        await self._db.flush()
        await self._db.refresh(row)
        return row

    async def get(self, scan_id: uuid.UUID) -> Scan | None:
        """Fetch by id. Returns None if no row exists or wrong org."""
        result = await self._db.execute(
            self._scoped(select(Scan).where(Scan.id == scan_id))
        )
        return result.scalar_one_or_none()

    async def get_latest_active(self) -> Scan | None:
        """Return the org's most-recently-updated non-terminal scan.

        Replaces Redis' ``scan_active:{org_id}`` pointer. Filters on a
        set of non-terminal statuses and orders by ``updated_at`` so a
        freshly-dispatched scan wins over a stale still-'running'
        row that simply never finished updating.
        """
        result = await self._db.execute(
            self._scoped(
                select(Scan).where(Scan.status.in_(_active_status_values()))
            ).order_by(Scan.updated_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def apply_update(
        self,
        scan_id: uuid.UUID,
        *,
        clamp_progress_to: int | None = None,
        append_repo_warning: dict[str, Any] | None = None,
        **fields: Any,
    ) -> Scan | None:
        """Partial update with monotonic progress + JSONB append.

        ``clamp_progress_to`` sets ``progress_pct = GREATEST(current,
        value)`` capped at 100 so the UI never regresses. Passing
        ``append_repo_warning`` pushes one dict onto the existing
        ``repo_warnings`` JSONB array without a read-modify-write
        round trip, so two concurrent callers can both land their
        warnings without one being lost.

        Returns the updated row, or ``None`` if the scan doesn't exist.
        """
        values: dict[str, Any] = {k: v for k, v in fields.items() if v is not None}
        if clamp_progress_to is not None:
            clamped = max(0, min(100, clamp_progress_to))
            values["progress_pct"] = func.greatest(Scan.progress_pct, clamped)
        if append_repo_warning is not None:
            # Concatenate a single-element JSONB array onto the existing
            # ``repo_warnings`` array atomically: ``repo_warnings || $1``.
            # The ``bindparam(type_=JSONB())`` is what gets us past two
            # footguns:
            #   1. asyncpg rejects ``jsonb_build_array($1)`` with
            #      ``IndeterminateDatatypeError`` when $1 is a Python
            #      dict — the protocol can't infer a type for an
            #      ``anyelement`` argument.
            #   2. ``cast(json.dumps([warning]), JSONB)`` encodes the
            #      string as a JSONB *scalar string* rather than
            #      parsing it as a JSONB array, so concatenation
            #      produces ``["[{...}]"]`` instead of ``[{...}]``.
            # A typed bindparam lets SQLAlchemy's JSONB TypeEngine
            # handle the serialisation end-to-end.
            values["repo_warnings"] = Scan.repo_warnings.op("||")(
                bindparam(
                    "append_repo_warning",
                    [append_repo_warning],
                    type_=JSONB(),
                )
            )
        if not values:
            return await self.get(scan_id)
        values["updated_at"] = datetime.now(UTC)

        stmt = (
            sql_update(Scan)
            .where(Scan.id == scan_id, Scan.org_id == self._org_id)
            .values(**values)
            .returning(Scan)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_stale_as_failed(self, scan_id: uuid.UUID) -> Scan | None:
        """If the scan has been silent past ``STALE_TIMEOUT``, flip it to failed.

        Run on read rather than from a scheduled task — cheap, and a
        stale scan doesn't surface anywhere until someone polls its
        status, so lazy eviction is fine.
        """
        cutoff = datetime.now(UTC) - STALE_TIMEOUT
        stmt = (
            sql_update(Scan)
            .where(
                Scan.id == scan_id,
                Scan.org_id == self._org_id,
                Scan.updated_at < cutoff,
                Scan.status.in_(_active_status_values()),
            )
            .values(
                status="failed",
                error=(
                    "Scan cancelled (timed out — no progress for "
                    f"{int(STALE_TIMEOUT.total_seconds() / 60)} minutes)."
                ),
                updated_at=datetime.now(UTC),
            )
            .returning(Scan)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()


def _active_status_values() -> list[str]:
    """String values of ``ACTIVE_SCAN_STATUSES`` for SQL ``IN (...)``."""
    return [s.value for s in ACTIVE_SCAN_STATUSES]
