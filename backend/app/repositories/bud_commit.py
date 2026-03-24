"""BUD commit tracking repository."""

import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud_commit import BUDCommit
from app.repositories.base import BaseRepository

logger = structlog.get_logger(__name__)


@dataclass
class RepoCommitSummary:
    """Summary of commits for one repo associated with a BUD."""

    repo_path: str
    commit_count: int
    first_sha: str
    last_sha: str


class BUDCommitRepository(BaseRepository[BUDCommit]):
    """Repository for BUD commit tracking, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(BUDCommit, db, org_id=org_id)

    async def create_commit(
        self,
        *,
        bud_id: uuid.UUID,
        repo_path: str,
        branch_name: str,
        commit_sha: str,
        commit_message: str,
        files_changed: str = "",
    ) -> BUDCommit | None:
        """Create a commit record, deduplicating by SHA via unique constraint.

        Uses INSERT + IntegrityError catch instead of check-then-act
        to avoid race conditions from concurrent post-commit hooks.

        Args:
            bud_id: BUD document UUID.
            repo_path: Absolute path of the repository.
            branch_name: Git branch name (e.g. bud-042/pay-later).
            commit_sha: Full 40-char commit hash.
            commit_message: First line of commit message.
            files_changed: Comma-separated list of changed files.

        Returns:
            The created BUDCommit, or None if duplicate.
        """
        commit = BUDCommit(
            org_id=self._org_id,
            bud_id=bud_id,
            repo_path=repo_path,
            branch_name=branch_name,
            commit_sha=commit_sha,
            commit_message=commit_message[:500],
            files_changed=files_changed[:5000],
        )
        try:
            created = await self.create(commit)
        except IntegrityError:
            await self._db.rollback()
            logger.debug("bud_commit_duplicate", sha=commit_sha[:8])
            return None
        return created

    async def list_repos_for_bud(self, bud_id: uuid.UUID) -> list[RepoCommitSummary]:
        """Get commit counts and chronological first/last SHAs grouped by repo for a BUD.

        Args:
            bud_id: The BUD document UUID.

        Returns:
            List of RepoCommitSummary with per-repo commit info.
        """
        # Use subqueries to get first/last SHA by created_at (not lexicographic)
        first_subq = self._scoped(
            select(
                BUDCommit.repo_path,
                BUDCommit.commit_sha,
                func.row_number()
                .over(partition_by=BUDCommit.repo_path, order_by=BUDCommit.created_at.asc())
                .label("rn"),
            ).where(BUDCommit.bud_id == bud_id)
        ).subquery()

        last_subq = self._scoped(
            select(
                BUDCommit.repo_path,
                BUDCommit.commit_sha,
                func.row_number()
                .over(partition_by=BUDCommit.repo_path, order_by=BUDCommit.created_at.desc())
                .label("rn"),
            ).where(BUDCommit.bud_id == bud_id)
        ).subquery()

        count_subq = self._scoped(
            select(
                BUDCommit.repo_path,
                func.count(BUDCommit.id).label("commit_count"),
            )
            .where(BUDCommit.bud_id == bud_id)
            .group_by(BUDCommit.repo_path)
        ).subquery()

        stmt = (
            select(
                count_subq.c.repo_path,
                count_subq.c.commit_count,
                first_subq.c.commit_sha.label("first_sha"),
                last_subq.c.commit_sha.label("last_sha"),
            )
            .join(first_subq, count_subq.c.repo_path == first_subq.c.repo_path)
            .join(last_subq, count_subq.c.repo_path == last_subq.c.repo_path)
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

    async def list_for_bud(self, bud_id: uuid.UUID, *, limit: int = 100) -> list[BUDCommit]:
        """List all commits for a BUD ordered by creation time.

        Args:
            bud_id: The BUD document UUID.
            limit: Maximum number of commits to return.

        Returns:
            List of BUDCommit records.
        """
        stmt = self._scoped(
            select(BUDCommit)
            .where(BUDCommit.bud_id == bud_id)
            .order_by(BUDCommit.created_at.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_last_sha_per_repo(self, bud_id: uuid.UUID) -> dict[str, str]:
        """Get the most recent commit SHA per repo for a BUD.

        Args:
            bud_id: The BUD document UUID.

        Returns:
            Dict mapping repo_path → latest commit SHA.
        """
        # Use a subquery to get max created_at per repo, then join back
        subq = self._scoped(
            select(
                BUDCommit.repo_path,
                func.max(BUDCommit.created_at).label("max_created"),
            )
            .where(BUDCommit.bud_id == bud_id)
            .group_by(BUDCommit.repo_path)
        ).subquery()
        stmt = self._scoped(
            select(BUDCommit.repo_path, BUDCommit.commit_sha)
            .join(
                subq,
                (BUDCommit.repo_path == subq.c.repo_path)
                & (BUDCommit.created_at == subq.c.max_created),
            )
            .where(BUDCommit.bud_id == bud_id)
        )
        result = await self._db.execute(stmt)
        return {row.repo_path: row.commit_sha for row in result.all()}
