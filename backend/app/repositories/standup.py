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

"""StandupReport data access repository."""

import uuid
from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.standup import StandupReport
from app.repositories.base import BaseRepository


class StandupReportRepository(BaseRepository[StandupReport]):
    """Repository for StandupReport rows, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(StandupReport, db, org_id=org_id)

    async def get_by_date(self, target_date: date) -> StandupReport | None:
        """Fetch the standup report for a specific date, if any."""
        stmt = self._scoped(select(StandupReport).where(StandupReport.date == target_date))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_recent(self, limit: int = 14) -> list[StandupReport]:
        """Most-recent standup reports for the org, newest first."""
        stmt = self._scoped(select(StandupReport)).order_by(StandupReport.date.desc()).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_previous_created_at(self, target_date: date) -> datetime | None:
        """``created_at`` of the most-recent standup strictly before ``target_date``.

        Used to derive the standup time window's lower bound. Returns
        ``None`` if no prior standup exists (caller falls back to a
        24-hour default).
        """
        stmt = (
            self._scoped(select(StandupReport.created_at))
            .where(StandupReport.date < target_date)
            .order_by(StandupReport.date.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
