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

"""``FeatureMatchLog`` data access — append-only reconciler decision trail.

Two responsibilities:

* :meth:`bulk_insert` — called once per reconcile run with the buffered
  ``match_log_rows`` from :class:`ReconcileResult`. Single round-trip.
* :meth:`list_for_repo` — drives the ``GET /v1/features/match-debug``
  endpoint. Supports filtering by repo, time window, match strategy,
  and score range so borderline Jaccard / cosine decisions can be
  audited against the 0.7 / 0.85 thresholds.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.feature_match_log import FeatureMatchLog


class FeatureMatchLogRepository:
    """Append-only repository for reconciler match decisions."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise with required org scope.

        Unlike :class:`WebhookLogRepository`, ``org_id`` is mandatory
        here: every match-log read is org-scoped and bulk inserts pass
        it on each row.
        """
        self._db = db
        self._org_id = org_id

    async def bulk_insert(self, rows: list[FeatureMatchLog]) -> None:
        """Insert a batch of match-log rows in one round-trip.

        Each row must already have ``org_id`` set on the model (the
        reconciler builds them this way). Empty input is a no-op.
        """
        if not rows:
            return
        self._db.add_all(rows)
        await self._db.flush()

    async def list_for_repo(
        self,
        *,
        repo_id: uuid.UUID | None = None,
        since: datetime | None = None,
        match_via: str | None = None,
        score_min: float | None = None,
        score_max: float | None = None,
        limit: int = 200,
    ) -> list[FeatureMatchLog]:
        """Recent match decisions for the configured org, newest first.

        Default ordering matches the borderline-tuning workflow: most
        recent decisions surface first so threshold drift after a code
        change is immediately visible. Caller is responsible for
        clamping ``limit`` to a sane upper bound (the endpoint enforces
        ``≤ 1000``).
        """
        stmt = (
            select(FeatureMatchLog)
            .where(FeatureMatchLog.org_id == self._org_id)
            .order_by(desc(FeatureMatchLog.created_at))
            .limit(limit)
        )
        if repo_id is not None:
            stmt = stmt.where(FeatureMatchLog.repo_id == repo_id)
        if since is not None:
            stmt = stmt.where(FeatureMatchLog.created_at >= since)
        if match_via is not None:
            stmt = stmt.where(FeatureMatchLog.match_via == match_via)
        if score_min is not None:
            stmt = stmt.where(FeatureMatchLog.score >= score_min)
        if score_max is not None:
            stmt = stmt.where(FeatureMatchLog.score <= score_max)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
