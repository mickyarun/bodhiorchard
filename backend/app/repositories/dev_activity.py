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

"""Developer activity log repository."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Select, String, and_, case, cast, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dev_activity import DevActivityLog
from app.models.role import Role
from app.models.tracked_repository import TrackedRepository
from app.models.user import OrgToUser
from app.repositories.base import BaseRepository


@dataclass
class RepoCommitSummary:
    """Summary of commits for one repo associated with a BUD."""

    repo_path: str
    commit_count: int
    first_sha: str
    last_sha: str


@dataclass
class UntrackedRepoSummary:
    """Summary of commits for one repo NOT in tracked_repositories.

    Used by the BUD detail testing tab to surface repos that the QA tester
    is pushing from but haven't been added to the org's tracked repos yet,
    with an "Add as tracked" CTA. Grouped by ``repo_path`` because we have
    no foreign key for these.
    """

    repo_path: str
    commit_count: int


@dataclass
class RepoContributor:
    """One row of a repo's all-time top-contributors panel.

    ``user_id`` is NULL when the activity rows are anonymous (webhook
    events that pre-date user attribution). ``actor_name`` is the
    git committer name written by the hook; we group by it as a
    fallback identity when ``user_id`` is NULL so anonymous commits
    still aggregate per-author instead of collapsing to one bucket.
    """

    user_id: uuid.UUID | None
    actor_name: str
    commit_count: int
    files_changed: int


def _apply_role_filter(
    stmt: Any,
    role: str | None,
    exclude_role: str | None,
) -> Any:
    """Apply optional committer-role filter to a SELECT statement.

    Effective role is computed at READ time by joining through
    ``org_to_user → roles``. The canonical role name lives in
    ``Role.name`` (set by the Members API via ``OrgToUser.role_id``); the
    legacy ``OrgToUser.role`` enum is used as a fallback for memberships
    that haven't been assigned a role_id yet (the enum defaults to
    ``developer``). The ``CASE`` expression below picks whichever is set.

    Semantics:
    - ``role="qa"`` → effective role == 'qa' (testing tab)
    - ``exclude_role="qa"`` → row has no user_id (anonymous events fall
      through to the dev-tab default) OR effective role != 'qa'
    - both None → no filter

    This approach eliminates the stale-snapshot drift we hit when
    ``actor_role`` was cached on ``dev_activity_logs``: the Members API
    only updates ``role_id``, never the enum column, so any snapshot
    reading the enum silently returned stale data.
    """
    if role is None and exclude_role is None:
        return stmt

    # LEFT JOIN so rows with user_id=NULL (anonymous webhook events) are
    # not dropped — they need to reach the exclude_role fall-through below.
    stmt = stmt.outerjoin(
        OrgToUser,
        and_(
            OrgToUser.user_id == DevActivityLog.user_id,
            OrgToUser.org_id == DevActivityLog.org_id,
        ),
    ).outerjoin(Role, Role.id == OrgToUser.role_id)

    # Prefer the canonical Role.name (set by the Members API) and fall
    # back to the legacy enum when role_id is unset. Users with no
    # membership at all produce NULL — they fall through to the dev tab
    # via the exclude_role branch below.
    #
    # The cast(..., String) is required because OrgToUser.role is a
    # Postgres enum type (user_role) while Role.name is varchar — CASE
    # branches must return the same type. Casting the enum to text is
    # free for Postgres and unifies the two branches.
    effective_role = case(
        (OrgToUser.role_id.is_not(None), Role.name),
        else_=cast(OrgToUser.role, String),
    )

    if role is not None:
        return stmt.where(effective_role == role)

    # exclude_role: anonymous events (no user_id) AND non-matching rows
    # both pass. The OR is critical — without it, a LEFT JOIN would
    # produce NULL comparisons that WHERE treats as false, silently
    # dropping legacy/unattributed activity.
    return stmt.where(
        or_(
            DevActivityLog.user_id.is_(None),
            effective_role != exclude_role,
        )
    )


class DevActivityLogRepository(BaseRepository[DevActivityLog]):
    """Repository for developer activity logs, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(DevActivityLog, db, org_id=org_id)

    async def map_shas_to_bud_ids(self, shas: list[str]) -> dict[str, uuid.UUID]:
        """Distinct ``sha -> bud_id`` mapping for matching commit SHAs."""
        if not shas:
            return {}
        stmt = self._scoped(
            select(DevActivityLog.commit_sha, DevActivityLog.bud_id).where(
                DevActivityLog.commit_sha.in_(shas),
                DevActivityLog.bud_id.is_not(None),
            )
        ).distinct()
        result = await self._db.execute(stmt)
        return {row[0]: row[1] for row in result.all() if row[0] and row[1]}

    async def count_events_by_user_in_window(
        self,
        event_types: list[str],
        since: datetime,
        until: datetime,
    ) -> dict[tuple[uuid.UUID, str], int]:
        """Count events grouped by ``(user_id, event_type)`` in a time window.

        Returns:
            Mapping of ``(user_id, event_type)`` tuples to counts. Rows
            with NULL ``user_id`` are excluded.
        """
        stmt = self._scoped(
            select(
                DevActivityLog.user_id,
                DevActivityLog.event_type,
                func.count().label("cnt"),
            )
            .where(
                DevActivityLog.created_at >= since,
                DevActivityLog.created_at < until,
                DevActivityLog.event_type.in_(event_types),
                DevActivityLog.user_id.isnot(None),
            )
            .group_by(DevActivityLog.user_id, DevActivityLog.event_type)
        )
        result = await self._db.execute(stmt)
        return {(row.user_id, row.event_type): row.cnt for row in result.all()}

    async def top_contributors_for_repo(
        self,
        repo_id: uuid.UUID,
        *,
        limit: int = 5,
    ) -> list[RepoContributor]:
        """All-time top contributors for one tracked repo.

        Aggregates commit events scoped by ``repo_id``: counts distinct
        commit SHAs per ``(user_id, actor_name)`` pair and sums the
        per-row file-change counts (``files_changed`` is a
        comma-separated path list — we count via Postgres
        ``array_length(string_to_array(…))``).

        Grouped by both ``user_id`` and ``actor_name`` so anonymous
        rows (NULL user_id, before user attribution rolled out) bucket
        per author instead of collapsing into a single anonymous row.
        Returns the top ``limit`` rows ordered by commit count
        descending.
        """
        DAL = DevActivityLog  # noqa: N806
        files_count = func.coalesce(
            func.array_length(
                func.string_to_array(func.coalesce(DAL.files_changed, ""), ","),
                1,
            ),
            0,
        )
        stmt = self._scoped(
            select(
                DAL.user_id,
                DAL.actor_name,
                func.count(func.distinct(DAL.commit_sha)).label("commit_count"),
                func.coalesce(func.sum(files_count), 0).label("files_changed"),
            )
            .where(
                DAL.repo_id == repo_id,
                DAL.event_type == "commit",
                DAL.commit_sha.is_not(None),
                DAL.actor_name.is_not(None),
            )
            .group_by(DAL.user_id, DAL.actor_name)
            .order_by(func.count(func.distinct(DAL.commit_sha)).desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [
            RepoContributor(
                user_id=row.user_id,
                actor_name=row.actor_name or "Unknown",
                commit_count=int(row.commit_count or 0),
                files_changed=int(row.files_changed or 0),
            )
            for row in result.all()
        ]

    async def commit_sha_exists(self, commit_sha: str) -> bool:
        """Return True if a commit event with this SHA is already recorded."""
        stmt = self._scoped(
            select(DevActivityLog.id)
            .where(
                DevActivityLog.event_type == "commit",
                DevActivityLog.commit_sha == commit_sha,
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def backfill_session_bud(self, session_id: str, bud_id: uuid.UUID) -> None:
        """Set ``bud_id`` on prior session events that lacked one."""
        stmt = (
            update(DevActivityLog)
            .where(
                DevActivityLog.session_id == session_id,
                DevActivityLog.org_id == self._org_id,
                DevActivityLog.bud_id.is_(None),
            )
            .values(bud_id=bud_id)
        )
        await self._db.execute(stmt)

    async def list_recent_branch_activity_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        limit: int = 200,
    ) -> list[tuple[str | None, str | None, uuid.UUID | None, str | None]]:
        """Recent branch-tagged dev events for a BUD.

        Returns ``(branch, actor_name, user_id, files_changed)`` tuples for
        the most recent ``limit`` rows that have a non-null ``branch``.
        Used to summarize cross-developer activity on a BUD's branches.
        """
        stmt = self._scoped(
            select(
                DevActivityLog.branch,
                DevActivityLog.actor_name,
                DevActivityLog.user_id,
                DevActivityLog.files_changed,
            )
            .where(
                DevActivityLog.bud_id == bud_id,
                DevActivityLog.branch.is_not(None),
            )
            .order_by(DevActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1], row[2], row[3]) for row in result.all()]

    def _commit_filter(
        self,
        bud_id: uuid.UUID,
    ) -> Select[tuple[DevActivityLog]]:
        """Base query for commit events linked to a BUD."""
        return self._scoped(
            select(DevActivityLog).where(
                DevActivityLog.bud_id == bud_id,
                DevActivityLog.event_type == "commit",
                DevActivityLog.commit_sha.is_not(None),
            )
        )

    async def list_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        limit: int = 100,
        role: str | None = None,
        exclude_role: str | None = None,
    ) -> list[DevActivityLog]:
        """List activity logs for a BUD, most recent first.

        Optional ``role`` / ``exclude_role`` filter on ``actor_role``. See
        ``_apply_role_filter`` for semantics. When both are None (default),
        every row is returned — preserves backward compatibility for callers
        that haven't migrated to the role-aware variants.
        """
        stmt = self._scoped(select(DevActivityLog).where(DevActivityLog.bud_id == bud_id))
        stmt = _apply_role_filter(stmt, role, exclude_role)
        stmt = stmt.order_by(DevActivityLog.created_at.desc()).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_commits_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        limit: int = 50,
        role: str | None = None,
        exclude_role: str | None = None,
    ) -> list[DevActivityLog]:
        """List commit events for a BUD, most recent first.

        Optional ``role`` / ``exclude_role`` filter — see ``list_for_bud``.
        """
        stmt = self._commit_filter(bud_id)
        stmt = _apply_role_filter(stmt, role, exclude_role)
        stmt = stmt.order_by(DevActivityLog.created_at.desc()).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_commit_repos_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        role: str | None = None,
        exclude_role: str | None = None,
    ) -> list[RepoCommitSummary]:
        """Get per-tracked-repo commit counts and first/last SHAs for a BUD.

        Joins on ``tracked_repositories``, so commits with ``repo_id IS NULL``
        (untracked repos) are EXCLUDED from this list — they're surfaced
        separately by ``list_untracked_repos_for_bud``. Optional role filter
        applies to all three subqueries so they stay in lockstep.
        """
        DAL = DevActivityLog  # noqa: N806
        TR = TrackedRepository  # noqa: N806

        # First SHA per repo (earliest created_at)
        first_stmt = self._scoped(
            select(
                DAL.repo_id,
                DAL.commit_sha,
                func.row_number()
                .over(partition_by=DAL.repo_id, order_by=DAL.created_at.asc())
                .label("rn"),
            ).where(
                DAL.bud_id == bud_id,
                DAL.event_type == "commit",
                DAL.commit_sha.is_not(None),
            )
        )
        first_subq = _apply_role_filter(first_stmt, role, exclude_role).subquery()

        # Last SHA per repo (latest created_at)
        last_stmt = self._scoped(
            select(
                DAL.repo_id,
                DAL.commit_sha,
                func.row_number()
                .over(partition_by=DAL.repo_id, order_by=DAL.created_at.desc())
                .label("rn"),
            ).where(
                DAL.bud_id == bud_id,
                DAL.event_type == "commit",
                DAL.commit_sha.is_not(None),
            )
        )
        last_subq = _apply_role_filter(last_stmt, role, exclude_role).subquery()

        # Count per repo
        count_stmt = self._scoped(
            select(
                DAL.repo_id,
                func.count(DAL.id).label("commit_count"),
            ).where(
                DAL.bud_id == bud_id,
                DAL.event_type == "commit",
                DAL.commit_sha.is_not(None),
            )
        )
        count_subq = (
            _apply_role_filter(count_stmt, role, exclude_role).group_by(DAL.repo_id).subquery()
        )

        stmt = (
            select(
                TR.path.label("repo_path"),
                count_subq.c.commit_count,
                first_subq.c.commit_sha.label("first_sha"),
                last_subq.c.commit_sha.label("last_sha"),
            )
            .join(first_subq, count_subq.c.repo_id == first_subq.c.repo_id)
            .join(last_subq, count_subq.c.repo_id == last_subq.c.repo_id)
            .join(TR, count_subq.c.repo_id == TR.id)
            .where(first_subq.c.rn == 1, last_subq.c.rn == 1)
        )
        result = await self._db.execute(stmt)
        return [
            RepoCommitSummary(
                repo_path=row.repo_path,
                commit_count=row.commit_count,
                first_sha=row.first_sha,
                last_sha=row.last_sha,
            )
            for row in result.all()
        ]

    async def list_untracked_repos_for_bud(
        self,
        bud_id: uuid.UUID,
        *,
        role: str | None = None,
        exclude_role: str | None = None,
    ) -> list[UntrackedRepoSummary]:
        """Get per-repo commit counts for repos NOT in tracked_repositories.

        Groups by ``repo_path`` (the raw filesystem path persisted on every
        activity row in Phase 2). Only rows with ``repo_id IS NULL`` AND
        ``repo_path IS NOT NULL`` are considered — i.e. the QA tester (or
        anyone else) ran Claude Code in a path the org hasn't added yet.
        """
        DAL = DevActivityLog  # noqa: N806
        stmt = self._scoped(
            select(
                DAL.repo_path,
                func.count(DAL.id).label("commit_count"),
            ).where(
                DAL.bud_id == bud_id,
                DAL.event_type == "commit",
                DAL.commit_sha.is_not(None),
                DAL.repo_id.is_(None),
                DAL.repo_path.is_not(None),
            )
        )
        stmt = _apply_role_filter(stmt, role, exclude_role)
        stmt = stmt.group_by(DAL.repo_path).order_by(func.count(DAL.id).desc())
        result = await self._db.execute(stmt)
        return [
            UntrackedRepoSummary(
                repo_path=row.repo_path,
                commit_count=row.commit_count,
            )
            for row in result.all()
        ]

    async def get_last_sha_per_repo(
        self,
        bud_id: uuid.UUID,
    ) -> dict[str, str]:
        """Get the most recent commit SHA per repo for a BUD.

        Returns:
            Dict mapping repo_path → latest commit SHA.
        """
        DAL = DevActivityLog  # noqa: N806
        TR = TrackedRepository  # noqa: N806

        subq = self._scoped(
            select(
                DAL.repo_id,
                func.max(DAL.created_at).label("max_created"),
            )
            .where(
                DAL.bud_id == bud_id,
                DAL.event_type == "commit",
                DAL.commit_sha.is_not(None),
            )
            .group_by(DAL.repo_id)
        ).subquery()

        # No _scoped on outer query — subquery already applies org_id filter
        stmt = (
            select(TR.path.label("repo_path"), DAL.commit_sha)
            .join(
                subq,
                (DAL.repo_id == subq.c.repo_id) & (DAL.created_at == subq.c.max_created),
            )
            .join(TR, DAL.repo_id == TR.id)
            .where(
                DAL.bud_id == bud_id,
                DAL.event_type == "commit",
                DAL.commit_sha.is_not(None),
            )
        )
        result = await self._db.execute(stmt)
        return {row.repo_path: row.commit_sha for row in result.all()}

    async def count_by_event_type(
        self,
        bud_id: uuid.UUID,
    ) -> dict[str, int]:
        """Count activity events by type for a BUD.

        Returns:
            Dict mapping event_type → count.
        """
        stmt = self._scoped(
            select(
                DevActivityLog.event_type,
                func.count(DevActivityLog.id).label("cnt"),
            )
            .where(DevActivityLog.bud_id == bud_id)
            .group_by(DevActivityLog.event_type)
        )
        result = await self._db.execute(stmt)
        return {row.event_type: row.cnt for row in result.all()}
