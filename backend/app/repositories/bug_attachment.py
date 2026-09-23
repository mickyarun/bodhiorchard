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

"""Repository for bug attachment CRUD operations."""

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bug_attachment import BugAttachment
from app.repositories.base import BaseRepository


class BugAttachmentRepository(BaseRepository[BugAttachment]):
    """Tenant-scoped repository for files attached to bugs."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(BugAttachment, db, org_id=org_id)

    async def list_for_bug(self, bug_id: uuid.UUID) -> list[BugAttachment]:
        """List a bug's attachments, oldest first.

        Ascending so the strip reads in the order the reporter added
        them — for a reproduction sequence of screenshots that order
        carries meaning, unlike the newest-first evidence list.
        """
        stmt = self._scoped(
            select(BugAttachment)
            .where(BugAttachment.bug_id == bug_id)
            .order_by(BugAttachment.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_for_bug(self, bug_id: uuid.UUID) -> int:
        """Count a bug's attachments, for the per-org max-files gate."""
        stmt = self._scoped(
            select(func.count()).select_from(BugAttachment).where(BugAttachment.bug_id == bug_id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one()
