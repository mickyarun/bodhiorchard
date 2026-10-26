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

"""Data access for the celebration-digest ledger."""

import uuid
from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.celebration_post import CelebrationPost, CelebrationPostStatus
from app.repositories.base import BaseRepository, rowcount

# Statuses whose ``covered_dates`` count as announced (or possibly
# announced) for de-duplication. A FAILED row's dates were not delivered,
# and only that row's own date may retry them.
_ANNOUNCED = (
    CelebrationPostStatus.CLAIMED,
    CelebrationPostStatus.SENT,
    CelebrationPostStatus.UNKNOWN,
)


class CelebrationPostRepository(BaseRepository[CelebrationPost]):
    """Posted celebration digests, always scoped to one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Tenant whose digests this repository exposes.
        """
        super().__init__(CelebrationPost, db, org_id=org_id)
        self._org = org_id

    async def get_for_date(self, celebrate_date: date) -> CelebrationPost | None:
        """The ledger row for one local date, if it has been claimed."""
        stmt = select(CelebrationPost).where(
            CelebrationPost.org_id == self._org,
            CelebrationPost.celebrate_date == celebrate_date,
        )
        return (await self._db.execute(stmt)).scalar_one_or_none()

    async def dates_announced_near(self, celebrate_date: date, *, span_days: int) -> set[date]:
        """Dates other posts within ``span_days`` of ``celebrate_date`` covered.

        Coverage is recomputed from the *current* settings each day, so after
        a weekend-policy or timezone change two neighbouring posts could both
        claim the same Saturday. Subtracting what neighbours already covered
        keeps every date announced at most once.
        """
        stmt = select(CelebrationPost.covered_dates).where(
            CelebrationPost.org_id == self._org,
            CelebrationPost.celebrate_date != celebrate_date,
            CelebrationPost.celebrate_date >= celebrate_date - timedelta(days=span_days),
            CelebrationPost.celebrate_date <= celebrate_date + timedelta(days=span_days),
            CelebrationPost.status.in_(_ANNOUNCED),
        )
        covered: set[date] = set()
        for (dates,) in (await self._db.execute(stmt)).all():
            covered.update(dates or ())
        return covered

    async def list_recent(self, limit: int = 14) -> list[CelebrationPost]:
        """The newest digests first — what the settings page shows as history."""
        stmt = (
            select(CelebrationPost)
            .where(CelebrationPost.org_id == self._org)
            .order_by(CelebrationPost.celebrate_date.desc())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def claim(
        self,
        celebrate_date: date,
        *,
        slack_channel_id: str,
        covered_dates: Iterable[date],
        birthday_count: int,
        anniversary_count: int,
    ) -> CelebrationPost:
        """Reserve ``celebrate_date`` before the Slack call goes out.

        Claiming first means a crash between the INSERT and the Slack API
        call loses that day's post rather than repeating it — the safer
        failure for something that pings a whole channel.

        Raises:
            sqlalchemy.exc.IntegrityError: Another worker claimed this date.
        """
        row = CelebrationPost(
            org_id=self._org,
            celebrate_date=celebrate_date,
            slack_channel_id=slack_channel_id,
            covered_dates=sorted(covered_dates),
            birthday_count=birthday_count,
            anniversary_count=anniversary_count,
            status=CelebrationPostStatus.CLAIMED,
            attempts=1,
        )
        self._db.add(row)
        await self._db.flush()
        return row

    async def claim_retry(self, row: CelebrationPost, *, slack_channel_id: str) -> bool:
        """Atomically move a FAILED row back to CLAIMED for another attempt.

        A compare-and-set on ``(status, attempts)``: two workers that both
        see the same failed row race this UPDATE, and only the one that
        matches a row gets ``True`` — the same exactly-once guarantee the
        unique constraint gives the first attempt.
        """
        result = await self._db.execute(
            sql_update(CelebrationPost)
            .where(
                CelebrationPost.id == row.id,
                CelebrationPost.org_id == self._org,
                CelebrationPost.status == CelebrationPostStatus.FAILED,
                CelebrationPost.attempts == row.attempts,
            )
            .values(
                status=CelebrationPostStatus.CLAIMED,
                attempts=row.attempts + 1,
                slack_channel_id=slack_channel_id,
            )
        )
        return (rowcount(result) or 0) == 1

    async def record_outcome(
        self,
        row_id: uuid.UUID,
        *,
        status: CelebrationPostStatus,
        message_ts: str | None = None,
        error: str | None = None,
    ) -> None:
        """Store how the Slack call for ``row_id`` ended."""
        await self._db.execute(
            sql_update(CelebrationPost)
            .where(CelebrationPost.id == row_id, CelebrationPost.org_id == self._org)
            .values(
                status=status,
                slack_message_ts=message_ts,
                last_error=(error or None) and error[:200],
            )
        )
