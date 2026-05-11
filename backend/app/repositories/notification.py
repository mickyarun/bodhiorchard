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

"""Notification data access repository."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification
from app.repositories.base import BaseRepository


class NotificationRepository(BaseRepository[Notification]):
    """Repository for user notifications, scoped by user_id.

    Overrides _scoped() to filter by user_id instead of org_id,
    ensuring all inherited BaseRepository methods are user-scoped.
    """

    def __init__(self, db: AsyncSession, *, user_id: uuid.UUID) -> None:
        super().__init__(Notification, db)
        self._user_id = user_id

    def _scoped(self, stmt: Select[tuple[Notification, ...]]) -> Select[tuple[Notification, ...]]:
        """Override: scope all queries by user_id instead of org_id."""
        return stmt.where(Notification.user_id == self._user_id)

    async def list_active(self, *, limit: int = 50, offset: int = 0) -> list[Notification]:
        """List non-dismissed notifications, newest first, with pagination."""
        stmt = self._scoped(
            select(Notification)
            .where(Notification.is_dismissed.is_(False))
            .order_by(Notification.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def unread_count(self) -> int:
        """Count of unread, non-dismissed notifications."""
        stmt = self._scoped(
            select(func.count(Notification.id))
            .where(Notification.is_read.is_(False))
            .where(Notification.is_dismissed.is_(False))
        )
        result = await self._db.execute(stmt)
        return result.scalar() or 0

    async def mark_read(self, notification_id: uuid.UUID) -> Notification | None:
        """Mark a single notification as read. Returns None if not found/not owned."""
        notif = await self.get_by_id(notification_id)
        if notif is None:
            return None
        notif.is_read = True
        await self._db.flush()
        return notif

    async def mark_all_read(self) -> int:
        """Mark all unread notifications as read. Returns count updated."""
        stmt = (
            update(Notification)
            .where(Notification.user_id == self._user_id)
            .where(Notification.is_read.is_(False))
            .values(is_read=True)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.rowcount

    async def dismiss(self, notification_id: uuid.UUID) -> bool:
        """Soft-dismiss a notification. Returns False if not found/not owned."""
        notif = await self.get_by_id(notification_id)
        if notif is None:
            return False
        notif.is_dismissed = True
        await self._db.flush()
        return True

    async def dismiss_all(self) -> int:
        """Dismiss all active notifications. Returns count updated."""
        stmt = (
            update(Notification)
            .where(Notification.user_id == self._user_id)
            .where(Notification.is_dismissed.is_(False))
            .values(is_dismissed=True)
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return result.rowcount

    async def cleanup_old(self, days: int = 30) -> int:
        """Hard-delete dismissed notifications older than N days."""
        cutoff = datetime.now(UTC) - timedelta(days=days)
        stmt = self._scoped(
            select(Notification)
            .where(Notification.is_dismissed.is_(True))
            .where(Notification.created_at < cutoff)
        )
        result = await self._db.execute(stmt)
        old = list(result.scalars().all())
        for n in old:
            await self._db.delete(n)
        if old:
            await self._db.flush()
        return len(old)
