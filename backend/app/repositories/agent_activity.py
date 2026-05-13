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

"""Agent activity log repository."""

import uuid
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_activity import AgentActivityLog
from app.models.bud import BUDDocument
from app.models.tracked_repository import TrackedRepository
from app.repositories.base import BaseRepository


async def list_orphan_phase_workers(
    db: AsyncSession, skill_slugs: list[str]
) -> list[AgentActivityLog]:
    """Return every cross-org phase-worker row left in the ``skill_invoked``
    state with no matching terminal event.

    Used once at app startup to reconcile orphans from a previous crash or
    restart — see ``agent_activity_logger.reconcile_orphan_phase_workers``.
    Module-level (not a repo method) because recovery is cross-tenant and
    runs before any org-scoped requests are served, mirroring
    ``recover_stuck_agent_tasks`` in ``bud_agent_task.py``.
    """
    if not skill_slugs:
        return []
    lifecycle_events = ("skill_invoked", "skill_completed", "skill_failed")
    # Latest lifecycle event per (org_id, bud_id, skill_slug).
    latest_per_triple = (
        select(
            AgentActivityLog.org_id,
            AgentActivityLog.bud_id,
            AgentActivityLog.skill_slug,
            func.max(AgentActivityLog.created_at).label("max_at"),
        )
        .where(AgentActivityLog.bud_id.isnot(None))
        .where(AgentActivityLog.skill_slug.in_(skill_slugs))
        .where(AgentActivityLog.event_type.in_(lifecycle_events))
        .group_by(
            AgentActivityLog.org_id,
            AgentActivityLog.bud_id,
            AgentActivityLog.skill_slug,
        )
        .subquery()
    )
    stmt = (
        select(AgentActivityLog)
        .join(
            latest_per_triple,
            (AgentActivityLog.org_id == latest_per_triple.c.org_id)
            & (AgentActivityLog.bud_id == latest_per_triple.c.bud_id)
            & (AgentActivityLog.skill_slug == latest_per_triple.c.skill_slug)
            & (AgentActivityLog.created_at == latest_per_triple.c.max_at),
        )
        .where(AgentActivityLog.event_type == "skill_invoked")
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


class AgentActivityLogRepository(BaseRepository[AgentActivityLog]):
    """Repository for agent activity logs, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(AgentActivityLog, db, org_id=org_id)

    async def list_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[AgentActivityLog]:
        """List agent activity logs for a BUD, most recent first."""
        stmt = self._scoped(
            select(AgentActivityLog)
            .where(AgentActivityLog.bud_id == bud_id)
            .order_by(AgentActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_skill_failed(
        self,
        bud_id: uuid.UUID,
        *,
        skill_slugs: list[str] | None = None,
        since: datetime | None = None,
    ) -> AgentActivityLog | None:
        """Return the most recent unresolved ``skill_failed`` row for a BUD.

        "Unresolved" means the LATEST lifecycle event for that slug on
        this BUD is ``skill_failed`` — if a ``skill_completed`` arrived
        after (e.g. the user retried and it succeeded), the failure is
        stale and we return nothing. Same shape as
        :meth:`get_active_phase_worker` but flipped: that one keeps rows
        where the latest is ``skill_invoked``; this one keeps rows where
        the latest is ``skill_failed``.

        ``since`` is the BUD's ``phase_failure_acknowledged_at`` — rows
        at or before the user's last dismissal are excluded so an
        acknowledged failure doesn't re-pop on refresh.
        """
        slug_filter = skill_slugs or []
        lifecycle_events = ("skill_invoked", "skill_completed", "skill_failed")
        latest_select = (
            select(
                AgentActivityLog.skill_slug,
                func.max(AgentActivityLog.created_at).label("max_at"),
            )
            .where(AgentActivityLog.bud_id == bud_id)
            .where(AgentActivityLog.event_type.in_(lifecycle_events))
        )
        if slug_filter:
            latest_select = latest_select.where(AgentActivityLog.skill_slug.in_(slug_filter))
        latest_per_slug = latest_select.group_by(AgentActivityLog.skill_slug).subquery()

        stmt = self._scoped(
            select(AgentActivityLog)
            .join(
                latest_per_slug,
                (AgentActivityLog.skill_slug == latest_per_slug.c.skill_slug)
                & (AgentActivityLog.created_at == latest_per_slug.c.max_at),
            )
            .where(AgentActivityLog.bud_id == bud_id)
            .where(AgentActivityLog.event_type == "skill_failed")
        )
        if since is not None:
            stmt = stmt.where(AgentActivityLog.created_at > since)
        stmt = stmt.order_by(AgentActivityLog.created_at.desc()).limit(1)
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def get_active_phase_worker(
        self,
        bud_id: uuid.UUID,
        skill_slugs: list[str],
    ) -> AgentActivityLog | None:
        """Return the most recent in-flight phase-worker event for a BUD.

        "In-flight" means the latest event for the given ``skill_slugs`` on
        this BUD is a ``skill_invoked`` row — i.e. no matching
        ``skill_completed`` or ``skill_failed`` arrived afterwards. Used by
        the BUD detail page to re-attach the progress banner after the
        user navigates away and back; the WS subscriber alone only sees
        events that fire AFTER mount, so without this seed the chain is
        invisible until the next stage starts.
        """
        if not skill_slugs:
            return None
        # Pick the latest lifecycle event for each skill_slug, then keep
        # only the rows where that latest event is `skill_invoked`.
        lifecycle_events = ("skill_invoked", "skill_completed", "skill_failed")
        latest_per_slug = (
            select(
                AgentActivityLog.skill_slug,
                func.max(AgentActivityLog.created_at).label("max_at"),
            )
            .where(AgentActivityLog.bud_id == bud_id)
            .where(AgentActivityLog.skill_slug.in_(skill_slugs))
            .where(AgentActivityLog.event_type.in_(lifecycle_events))
            .group_by(AgentActivityLog.skill_slug)
            .subquery()
        )
        stmt = self._scoped(
            select(AgentActivityLog)
            .join(
                latest_per_slug,
                (AgentActivityLog.skill_slug == latest_per_slug.c.skill_slug)
                & (AgentActivityLog.created_at == latest_per_slug.c.max_at),
            )
            .where(AgentActivityLog.bud_id == bud_id)
            .where(AgentActivityLog.event_type == "skill_invoked")
            .order_by(AgentActivityLog.created_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_for_skill(
        self,
        skill_id: uuid.UUID,
        *,
        limit: int = 100,
    ) -> list[AgentActivityLog]:
        """List agent activity logs for a skill, most recent first."""
        stmt = self._scoped(
            select(AgentActivityLog)
            .where(AgentActivityLog.skill_id == skill_id)
            .order_by(AgentActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_recent_with_repo_bud(
        self, event_types: list[str], *, limit: int = 10
    ) -> list[tuple[AgentActivityLog, str | None, int | None, str | None]]:
        """Recent activity rows joined with repo name and BUD info.

        Returns ``(log, repo_name, bud_number, bud_title)`` tuples.
        """
        stmt = self._scoped(
            select(
                AgentActivityLog,
                TrackedRepository.name.label("repo_name"),
                BUDDocument.bud_number.label("bud_number"),
                BUDDocument.title.label("bud_title"),
            )
            .outerjoin(TrackedRepository, AgentActivityLog.repo_id == TrackedRepository.id)
            .outerjoin(BUDDocument, AgentActivityLog.bud_id == BUDDocument.id)
            .where(AgentActivityLog.event_type.in_(event_types))
            .order_by(AgentActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [(row[0], row.repo_name, row.bud_number, row.bud_title) for row in result.all()]

    async def count_skill_completions_by_user_in_window(
        self, since: datetime, until: datetime
    ) -> dict[uuid.UUID, int]:
        """Count ``skill_completed`` events per user in [since, until)."""
        stmt = self._scoped(
            select(AgentActivityLog.user_id, func.count().label("cnt"))
            .where(
                AgentActivityLog.event_type == "skill_completed",
                AgentActivityLog.created_at >= since,
                AgentActivityLog.created_at < until,
                AgentActivityLog.user_id.isnot(None),
            )
            .group_by(AgentActivityLog.user_id)
        )
        result = await self._db.execute(stmt)
        return {row.user_id: row.cnt for row in result.all()}

    async def commit_sha_exists(self, commit_sha: str) -> bool:
        """Return True if a commit event with this SHA is already recorded."""
        stmt = self._scoped(
            select(AgentActivityLog.id)
            .where(
                AgentActivityLog.event_type == "commit",
                AgentActivityLog.commit_sha == commit_sha,
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def backfill_session_bud(self, session_id: str, bud_id: uuid.UUID) -> None:
        """Set ``bud_id`` on prior session events that lacked one.

        Hooks may emit events before a BUD has been resolved (e.g. before
        a branch matches a BUD pattern). When a later event in the same
        session does resolve a BUD, we retroactively link the earlier
        events so the activity timeline is complete.
        """
        stmt = (
            update(AgentActivityLog)
            .where(
                AgentActivityLog.session_id == session_id,
                AgentActivityLog.org_id == self._org_id,
                AgentActivityLog.bud_id.is_(None),
            )
            .values(bud_id=bud_id)
        )
        await self._db.execute(stmt)

    async def list_for_session(
        self,
        session_id: str,
    ) -> list[AgentActivityLog]:
        """List all agent activity events in a session."""
        stmt = self._scoped(
            select(AgentActivityLog)
            .where(AgentActivityLog.session_id == session_id)
            .order_by(AgentActivityLog.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
