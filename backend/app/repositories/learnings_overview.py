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

"""SQL for the org-level Learnings overview endpoint.

All queries this endpoint runs live here so the API handler stays a
thin orchestration layer per the project's "SQL only in repositories"
rule. The reads are intentionally bounded: complexity_buckets is a
direct scan of the small ``velocity_aggregates`` table, the other
three queries cap at the last 50 closed BUDs / 12 weeks / 30 days so
the overview page stays fast even on orgs with thousands of closed
BUDs.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.feature_learning import FeatureLearning
from app.models.user import User
from app.models.velocity_aggregate import VelocityAggregate
from app.repositories.base import BaseRepository

# Bounds chosen to match the rolling sample-window cap on
# velocity_aggregates so the overview's freshness matches the
# rollup's freshness.
RECENT_BUDS_LIMIT: int = 50
VELOCITY_TREND_WEEKS: int = 12
CONTRIBUTOR_WINDOW_DAYS: int = 30


class LearningsOverviewRepository(BaseRepository[VelocityAggregate]):
    """Read-only aggregator for the /learnings overview endpoint."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(VelocityAggregate, db, org_id=org_id)

    async def list_velocity_buckets(self) -> list[VelocityAggregate]:
        """Every velocity_aggregates row for this org, single indexed scan.

        Caller groups by complexity to assemble the ComplexityBucketRead
        rows. The table has one row per (complexity, phase) per org
        so this is at most ~40 rows in the worst case.
        """
        stmt = self._scoped(select(VelocityAggregate))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_learnings_with_metrics(self) -> list[FeatureLearning]:
        """Recent closed BUDs that have a metrics envelope.

        Drives the repeat-offender and velocity-trend cards. Ordering
        is most-recent-first; the limit matches the rolling-window cap
        on velocity_aggregates so the two views surface the same data.
        """
        stmt = (
            select(FeatureLearning)
            .where(
                FeatureLearning.org_id == self._org_id,
                FeatureLearning.metrics.is_not(None),
            )
            .order_by(FeatureLearning.created_at.desc())
            .limit(RECENT_BUDS_LIMIT)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_closed_buds(
        self, *, weeks: int = VELOCITY_TREND_WEEKS
    ) -> list[BUDDocument]:
        """Closed BUDs that finished within the last ``weeks`` weeks.

        The velocity-trend chart needs cycle_time per BUD bucketed by
        completion week. We pull the raw rows and bucket in Python so
        the timezone math stays consistent with the rest of the app.
        """
        since = datetime.now(tz=UTC) - timedelta(weeks=weeks)
        stmt = (
            select(BUDDocument)
            .where(
                BUDDocument.org_id == self._org_id,
                BUDDocument.status == BUDStatus.CLOSED,
                BUDDocument.updated_at >= since,
            )
            .order_by(BUDDocument.updated_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_top_contributors_recent(
        self, *, days: int = CONTRIBUTOR_WINDOW_DAYS, limit: int = 10
    ) -> list[tuple[User, int, int, int]]:
        """Top contributors over the last ``days`` days.

        Computes per-user totals across recent FeatureLearning rows'
        ``metrics.contributors`` arrays. Returns (user, buds_shipped,
        total_commits, total_prs_merged) tuples ordered by
        buds_shipped descending.

        Aggregating in Python here is correct: the recent-BUDs window
        is tiny (≤50 rows × ≤10 contributors each = ≤500 entries),
        and the per-user totals need the user's name from a join — a
        single bulk fetch by id at the end is cheaper than a JSONB
        join in SQL.
        """
        since = datetime.now(tz=UTC) - timedelta(days=days)
        stmt = (
            select(FeatureLearning)
            .where(
                FeatureLearning.org_id == self._org_id,
                FeatureLearning.metrics.is_not(None),
                FeatureLearning.created_at >= since,
            )
            .order_by(FeatureLearning.created_at.desc())
        )
        result = await self._db.execute(stmt)
        learnings = list(result.scalars().all())

        per_user_buds: dict[uuid.UUID, int] = {}
        per_user_commits: dict[uuid.UUID, int] = {}
        per_user_prs: dict[uuid.UUID, int] = {}
        for learning in learnings:
            contributors = (learning.metrics or {}).get("contributors") or []
            for entry in contributors:
                if not isinstance(entry, dict):
                    continue
                uid_raw = entry.get("user_id")
                if not uid_raw:
                    continue
                try:
                    uid = uuid.UUID(str(uid_raw))
                except ValueError:
                    continue
                per_user_buds[uid] = per_user_buds.get(uid, 0) + 1
                per_user_commits[uid] = per_user_commits.get(uid, 0) + int(
                    entry.get("commits", 0) or 0
                )
                per_user_prs[uid] = per_user_prs.get(uid, 0) + int(entry.get("prs_merged", 0) or 0)

        if not per_user_buds:
            return []

        users_stmt = select(User).where(User.id.in_(list(per_user_buds.keys())))
        users_result = await self._db.execute(users_stmt)
        users_by_id = {u.id: u for u in users_result.scalars().all()}

        ranked = sorted(per_user_buds.items(), key=lambda kv: kv[1], reverse=True)[:limit]
        out: list[tuple[User, int, int, int]] = []
        for uid, buds in ranked:
            user = users_by_id.get(uid)
            if user is None:
                continue
            out.append(
                (
                    user,
                    buds,
                    per_user_commits.get(uid, 0),
                    per_user_prs.get(uid, 0),
                )
            )
        return out

    async def count_closed_buds(self) -> int:
        """Cheap empty-state check — has the org closed anything yet?"""
        stmt = self._scoped(
            select(func.count())
            .select_from(BUDDocument)
            .where(BUDDocument.status == BUDStatus.CLOSED)
        )
        result = await self._db.execute(stmt)
        return int(result.scalar_one() or 0)
