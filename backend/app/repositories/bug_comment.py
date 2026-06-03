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

"""Data access for the :class:`app.models.bug_comment.BugComment` thread."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bug_comment import BugComment
from app.repositories.base import BaseRepository


class BugCommentRepository(BaseRepository[BugComment]):
    """Repository for bug-comment queries, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(BugComment, db, org_id=org_id)

    async def list_for_bug(
        self, bug_id: uuid.UUID, *, include_deleted: bool = True
    ) -> list[BugComment]:
        """All comments on a bug, oldest first (thread order).

        Soft-deleted comments are included by default so the UI can
        render a "[deleted]" tombstone in-place; callers that want a
        clean export should pass ``include_deleted=False``.
        """
        stmt = self._scoped(
            select(BugComment)
            .where(BugComment.bug_id == bug_id)
            .order_by(BugComment.created_at.asc())
        )
        if not include_deleted:
            stmt = stmt.where(BugComment.deleted_at.is_(None))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_active_by_bug(self, bug_ids: list[uuid.UUID]) -> dict[uuid.UUID, int]:
        """Bulk-count non-deleted comments per bug id.

        Used by the board card badge ("3 comments"). Bugs with no
        comments are absent from the returned dict.
        """
        if not bug_ids:
            return {}
        stmt = self._scoped(
            select(BugComment.bug_id, func.count(BugComment.id))
            .where(BugComment.bug_id.in_(bug_ids), BugComment.deleted_at.is_(None))
            .group_by(BugComment.bug_id)
        )
        result = await self._db.execute(stmt)
        return {row[0]: row[1] for row in result.all()}

    async def update_body(self, comment: BugComment, body: str) -> BugComment:
        """Edit a comment's body and stamp ``edited_at``."""
        comment.body = body
        comment.edited_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(comment)
        return comment

    async def soft_delete(self, comment: BugComment) -> BugComment:
        """Tombstone a comment without removing the row.

        Audit trail and any future notification follow-ups need the
        original author + timestamp; the UI renders ``[deleted]`` when
        ``deleted_at`` is set.
        """
        comment.deleted_at = datetime.now(UTC)
        await self._db.flush()
        await self._db.refresh(comment)
        return comment
