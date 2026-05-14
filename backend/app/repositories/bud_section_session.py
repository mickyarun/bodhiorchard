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

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud_section_session import BUDSectionSession
from app.repositories.base import BaseRepository


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
