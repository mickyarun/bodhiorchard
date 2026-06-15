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

"""Quiz topic-history data access — org-scoped non-repetition ledger."""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz_topic_history import QuizTopicHistory


class QuizTopicHistoryRepository:
    """Repository scoped by org_id — keeps cross-org queries impossible."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        self._db = db
        self._org_id = org_id

    async def recent_labels(self, *, since: date, limit: int = 100) -> list[str]:
        """Human-readable topic labels used on/after ``since`` — the agent denylist."""
        stmt = (
            select(QuizTopicHistory.topic_label)
            .where(QuizTopicHistory.org_id == self._org_id)
            .where(QuizTopicHistory.last_used_date >= since)
            .order_by(QuizTopicHistory.last_used_date.desc())
            .limit(limit)
        )
        return list((await self._db.execute(stmt)).scalars().all())

    async def existing_hashes(self, hashes: list[str]) -> set[str]:
        """Subset of ``hashes`` already present for this org (hard non-repeat check)."""
        if not hashes:
            return set()
        stmt = (
            select(QuizTopicHistory.topic_hash)
            .where(QuizTopicHistory.org_id == self._org_id)
            .where(QuizTopicHistory.topic_hash.in_(hashes))
        )
        return set((await self._db.execute(stmt)).scalars().all())

    async def upsert(self, *, topic_hash: str, topic_label: str, used_date: date) -> None:
        """Record (or refresh) a topic as used. Idempotent on (org_id, topic_hash)."""
        stmt = (
            select(QuizTopicHistory)
            .where(QuizTopicHistory.org_id == self._org_id)
            .where(QuizTopicHistory.topic_hash == topic_hash)
            .with_for_update()
        )
        existing = (await self._db.execute(stmt)).scalar_one_or_none()
        if existing is not None:
            existing.topic_label = topic_label
            existing.last_used_date = used_date
            await self._db.flush()
            return

        row = QuizTopicHistory(
            org_id=self._org_id,
            topic_hash=topic_hash,
            topic_label=topic_label,
            last_used_date=used_date,
        )
        try:
            async with self._db.begin_nested():
                self._db.add(row)
        except IntegrityError:
            existing = (await self._db.execute(stmt)).scalar_one_or_none()
            if existing is not None:
                existing.topic_label = topic_label
                existing.last_used_date = used_date
                await self._db.flush()
