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

"""Claiming and recording the daily who's-out post."""

import uuid
from datetime import date, timedelta

from sqlalchemy import and_, func, or_, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_digest_post import DigestStatus, LeaveDigestPost

MAX_ATTEMPTS = 3
# A claim this old with no outcome was abandoned (crash or restart).
STALE_CLAIM = timedelta(minutes=5)


class LeaveDigestPostRepository:
    """Daily post rows for one org."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        self._db = db
        self._org = org_id

    async def claim(self, local_date: date) -> bool:
        """Take the day's post: True for a first claim, or a retry after a failure
        or an abandoned claim."""
        inserted = await self._db.execute(
            insert(LeaveDigestPost)
            .values(
                id=uuid.uuid4(),
                org_id=self._org,
                local_date=local_date,
                status=DigestStatus.CLAIMED,
                attempts=1,
            )
            .on_conflict_do_nothing(constraint="uq_leave_digest_posts_org_date")
            .returning(LeaveDigestPost.id)
        )
        if inserted.scalar_one_or_none() is not None:
            return True
        retried = await self._db.execute(
            update(LeaveDigestPost)
            .where(
                LeaveDigestPost.org_id == self._org,
                LeaveDigestPost.local_date == local_date,
                LeaveDigestPost.attempts < MAX_ATTEMPTS,
                or_(
                    LeaveDigestPost.status == DigestStatus.FAILED,
                    # A claim nobody finished (the process died mid-post).
                    and_(
                        LeaveDigestPost.status == DigestStatus.CLAIMED,
                        LeaveDigestPost.updated_at < func.now() - STALE_CLAIM,
                    ),
                ),
            )
            .values(status=DigestStatus.CLAIMED, attempts=LeaveDigestPost.attempts + 1)
            .returning(LeaveDigestPost.id)
        )
        return retried.scalar_one_or_none() is not None

    async def finish(self, local_date: date, status: DigestStatus, error: str | None) -> None:
        """Record how the claimed post ended."""
        await self._db.execute(
            update(LeaveDigestPost)
            .where(LeaveDigestPost.org_id == self._org, LeaveDigestPost.local_date == local_date)
            .values(status=status, error=error)
        )
