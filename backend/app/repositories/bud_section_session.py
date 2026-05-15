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

"""Repository for ``bud_section_sessions`` rows.

Lives in its own module so :mod:`app.repositories.bud` doesn't grow past
the project's file-size budget. All SQL for the section-session table
stays here — services and handlers consume the repository methods only.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud_section_session import BUDSectionSession, ChatActiveJobStatus
from app.repositories.base import BaseRepository


@dataclass(frozen=True, slots=True)
class ActiveJobPointer:
    """DTO for the durable in-flight job pointer on a section row."""

    job_id: str
    status: ChatActiveJobStatus
    started_at: datetime


@dataclass(frozen=True, slots=True)
class ClaimResult:
    """Outcome of an atomic ``try_claim_active_job`` call.

    ``won`` is True when the caller now holds the claim (either the row
    was inserted fresh with our ``job_id``, or an existing free row was
    updated to point at it). When False, the caller can fetch the
    current pointer separately via :meth:`get_active_job_pointer`.
    """

    won: bool
    session_id: uuid.UUID | None


class BUDSectionSessionRepository(BaseRepository[BUDSectionSession]):
    """Per-section originating-agent Claude CLI session bookkeeping."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(BUDSectionSession, db, org_id=org_id)

    async def get_active(
        self,
        bud_id: uuid.UUID,
        section: str,
        design_id: uuid.UUID | None = None,
    ) -> BUDSectionSession | None:
        """Return the active session row for a (bud, section[, design]) thread.

        ``design_id`` is treated as part of the key when supplied. For
        non-design sections (``design_id is None``) the row matches when
        the stored column is also ``NULL``.
        """
        stmt = self._scoped(
            select(BUDSectionSession)
            .where(BUDSectionSession.bud_id == bud_id)
            .where(BUDSectionSession.section == section)
        )
        if design_id is None:
            stmt = stmt.where(BUDSectionSession.design_id.is_(None))
        else:
            stmt = stmt.where(BUDSectionSession.design_id == design_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def upsert(
        self,
        bud_id: uuid.UUID,
        section: str,
        session_id: uuid.UUID,
        design_id: uuid.UUID | None = None,
    ) -> BUDSectionSession:
        """Create the session row if absent, otherwise update its ``session_id``.

        Resetting an existing row clears ``message_count`` so the resume
        cap counts only turns made against the new session id. Caller is
        responsible for committing the surrounding transaction.
        """
        existing = await self.get_active(bud_id, section, design_id)
        if existing is not None:
            existing.session_id = session_id
            existing.message_count = 0
            await self._db.flush()
            await self._db.refresh(existing)
            return existing

        row = BUDSectionSession(
            org_id=self._org_id,
            bud_id=bud_id,
            section=section,
            design_id=design_id,
            session_id=session_id,
            message_count=0,
        )
        return await self.create(row)

    async def increment_message_count(self, row_id: uuid.UUID) -> None:
        """Bump ``message_count`` by one on the given row."""
        row = await self.get_by_id(row_id)
        if row is None:
            return
        row.message_count += 1
        await self._db.flush()

    async def rotate(
        self,
        row_id: uuid.UUID,
        new_session_id: uuid.UUID,
    ) -> BUDSectionSession | None:
        """Replace ``session_id`` and reset ``message_count`` to zero.

        Returns the refreshed row, or ``None`` if it has been deleted
        between the cap check and the rotation call (e.g. BUD cascade).
        """
        row = await self.get_by_id(row_id)
        if row is None:
            return None
        row.session_id = new_session_id
        row.message_count = 0
        await self._db.flush()
        await self._db.refresh(row)
        return row

    # ── In-flight chat-job claim ────────────────────────────────────

    async def try_claim_active_job(
        self,
        bud_id: uuid.UUID,
        section: str,
        design_id: uuid.UUID | None,
        job_id: str,
        *,
        fallback_session_id: uuid.UUID | None = None,
    ) -> ClaimResult:
        """Atomically ensure a session row exists and claim its job slot.

        Single statement: ``INSERT ... ON CONFLICT DO UPDATE SET ...``
        where the UPDATE branch is gated by ``active_job_id IS NULL``.
        Postgres serialises concurrent writes on the matching partial
        unique index, so exactly one caller wins the claim for a given
        ``(bud, section, design_id)`` triple. The other caller's
        RETURNING is empty and we surface that as ``won=False`` so the
        endpoint can respond 409 with the current pointer.

        If the row needs to be created (no chat has ever run for this
        section yet), ``fallback_session_id`` is used as the seed
        ``session_id`` — the worker is free to rotate it on first turn.
        When omitted, a fresh UUID is minted.
        """
        seed_session_id = fallback_session_id or uuid.uuid4()
        values: dict[str, object] = {
            "org_id": self._org_id,
            "bud_id": bud_id,
            "section": section,
            "design_id": design_id,
            "session_id": seed_session_id,
            "message_count": 0,
            "active_job_id": job_id,
            "active_job_status": ChatActiveJobStatus.QUEUED,
            "active_job_started_at": func.now(),
        }

        # The model uses two partial unique indexes — one for
        # ``design_id IS NULL`` and one for ``design_id IS NOT NULL`` —
        # because PG 14 lacks ``UNIQUE NULLS NOT DISTINCT``. The
        # ON CONFLICT target must pick the matching one.
        if design_id is None:
            index_elements = ["bud_id", "section"]
            index_where = text("design_id IS NULL")
        else:
            index_elements = ["bud_id", "section", "design_id"]
            index_where = text("design_id IS NOT NULL")

        stmt = (
            pg_insert(BUDSectionSession)
            .values(**values)
            .on_conflict_do_update(
                index_elements=index_elements,
                index_where=index_where,
                set_={
                    "active_job_id": job_id,
                    "active_job_status": ChatActiveJobStatus.QUEUED,
                    "active_job_started_at": func.now(),
                },
                where=(
                    BUDSectionSession.active_job_id.is_(None)
                    & (BUDSectionSession.org_id == self._org_id)
                ),
            )
            .returning(BUDSectionSession.session_id)
        )
        result = await self._db.execute(stmt)
        row = result.first()
        if row is None:
            return ClaimResult(won=False, session_id=None)
        return ClaimResult(won=True, session_id=row.session_id)

    async def mark_active_job_running(
        self,
        bud_id: uuid.UUID,
        section: str,
        design_id: uuid.UUID | None,
    ) -> None:
        """Flip ``active_job_status`` from QUEUED to RUNNING on the row.

        Called by the chat worker as soon as it picks the job off the
        queue. The status is informational — the resume flow uses
        ``active_job_id`` for re-subscribe and looks up live state in
        ``_job_store`` for the actual progress message.
        """
        stmt = (
            update(BUDSectionSession)
            .where(BUDSectionSession.org_id == self._org_id)
            .where(BUDSectionSession.bud_id == bud_id)
            .where(BUDSectionSession.section == section)
            .where(BUDSectionSession.active_job_id.is_not(None))
            .values(active_job_status=ChatActiveJobStatus.RUNNING)
        )
        if design_id is None:
            stmt = stmt.where(BUDSectionSession.design_id.is_(None))
        else:
            stmt = stmt.where(BUDSectionSession.design_id == design_id)
        await self._db.execute(stmt)

    async def clear_active_job(
        self,
        bud_id: uuid.UUID,
        section: str,
        design_id: uuid.UUID | None,
    ) -> None:
        """Release the in-flight pointer on the section row.

        Worker terminal path calls this after the WS frame for COMPLETED
        / FAILED / CANCELLED has been published. Best-effort: a failure
        here is logged but does not block the user from seeing their
        result — the boot-time orphan sweep is the durable backstop.
        """
        stmt = (
            update(BUDSectionSession)
            .where(BUDSectionSession.org_id == self._org_id)
            .where(BUDSectionSession.bud_id == bud_id)
            .where(BUDSectionSession.section == section)
            .values(
                active_job_id=None,
                active_job_status=None,
                active_job_started_at=None,
            )
        )
        if design_id is None:
            stmt = stmt.where(BUDSectionSession.design_id.is_(None))
        else:
            stmt = stmt.where(BUDSectionSession.design_id == design_id)
        await self._db.execute(stmt)

    async def get_active_job_pointer(
        self,
        bud_id: uuid.UUID,
        section: str,
        design_id: uuid.UUID | None,
    ) -> ActiveJobPointer | None:
        """Return the in-flight job pointer for the section, or None.

        Surfaces the durable side of the claim; the live frame state
        lives in ``_job_store`` and is fetched separately by the
        active-job endpoint.
        """
        row = await self.get_active(bud_id, section, design_id)
        if row is None or row.active_job_id is None:
            return None
        if row.active_job_status is None or row.active_job_started_at is None:
            # Should never happen — the three fields are written together
            # by ``try_claim_active_job`` and cleared together by
            # ``clear_active_job``. Defensive null check just to satisfy
            # the type narrowing.
            return None
        return ActiveJobPointer(
            job_id=row.active_job_id,
            status=row.active_job_status,
            started_at=row.active_job_started_at,
        )
