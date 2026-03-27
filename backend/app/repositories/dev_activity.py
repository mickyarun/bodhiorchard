"""Developer activity log repository."""

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dev_activity import DevActivityLog
from app.models.tracked_repository import TrackedRepository
from app.repositories.base import BaseRepository


@dataclass
class RepoCommitSummary:
    """Summary of commits for one repo associated with a BUD."""

    repo_path: str
    commit_count: int
    first_sha: str
    last_sha: str


class DevActivityLogRepository(BaseRepository[DevActivityLog]):
    """Repository for developer activity logs, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(DevActivityLog, db, org_id=org_id)

    def _commit_filter(
        self, bud_id: uuid.UUID,
    ) -> Select[tuple[DevActivityLog, ...]]:
        """Base query for commit events linked to a BUD."""
        return self._scoped(
            select(DevActivityLog).where(
                DevActivityLog.bud_id == bud_id,
                DevActivityLog.event_type == "commit",
                DevActivityLog.commit_sha.is_not(None),
            )
        )

    async def list_for_bud(
        self, bud_id: uuid.UUID, *, limit: int = 100,
    ) -> list[DevActivityLog]:
        """List activity logs for a BUD, most recent first."""
        stmt = self._scoped(
            select(DevActivityLog)
            .where(DevActivityLog.bud_id == bud_id)
            .order_by(DevActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_commits_for_bud(
        self, bud_id: uuid.UUID, *, limit: int = 50,
    ) -> list[DevActivityLog]:
        """List commit events for a BUD, most recent first."""
        stmt = (
            self._commit_filter(bud_id)
            .order_by(DevActivityLog.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_commit_repos_for_bud(
        self, bud_id: uuid.UUID,
    ) -> list[RepoCommitSummary]:
        """Get per-repo commit counts and first/last SHAs for a BUD."""
        DAL = DevActivityLog  # noqa: N806
        TR = TrackedRepository  # noqa: N806

        # First SHA per repo (earliest created_at)
        first_subq = (
            self._scoped(
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
            .subquery()
        )

        # Last SHA per repo (latest created_at)
        last_subq = (
            self._scoped(
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
            .subquery()
        )

        # Count per repo
        count_subq = (
            self._scoped(
                select(
                    DAL.repo_id,
                    func.count(DAL.id).label("commit_count"),
                )
                .where(
                    DAL.bud_id == bud_id,
                    DAL.event_type == "commit",
                    DAL.commit_sha.is_not(None),
                )
                .group_by(DAL.repo_id)
            )
            .subquery()
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

    async def get_last_sha_per_repo(
        self, bud_id: uuid.UUID,
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
                (DAL.repo_id == subq.c.repo_id)
                & (DAL.created_at == subq.c.max_created),
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
        self, bud_id: uuid.UUID,
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
