"""Pull request repository for GitHub PR tracking."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PRState, PullRequest
from app.repositories.base import BaseRepository


class PullRequestRepository(BaseRepository[PullRequest]):
    """Repository for pull requests, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(PullRequest, db, org_id=org_id)

    async def get_by_github_pr_id(self, github_pr_id: int) -> PullRequest | None:
        """Look up a PR by its GitHub global ID."""
        stmt = self._scoped(select(PullRequest).where(PullRequest.github_pr_id == github_pr_id))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[PullRequest]:
        """List all PRs linked to a BUD, newest first."""
        stmt = self._scoped(
            select(PullRequest)
            .where(PullRequest.bud_id == bud_id)
            .order_by(PullRequest.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_open_for_bud(self, bud_id: uuid.UUID) -> list[PullRequest]:
        """List open (non-merged, non-closed) PRs for a BUD."""
        stmt = self._scoped(
            select(PullRequest).where(
                PullRequest.bud_id == bud_id,
                PullRequest.state == PRState.OPEN,
            )
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_repo_ids_with_prs(self, bud_id: uuid.UUID) -> set[str]:
        """Get set of repo_id strings that have at least one PR for this BUD."""
        stmt = self._scoped(
            select(PullRequest.repo_id).where(
                PullRequest.bud_id == bud_id,
                PullRequest.repo_id.is_not(None),
            )
        ).distinct()
        result = await self._db.execute(stmt)
        return {str(row[0]) for row in result.all()}
