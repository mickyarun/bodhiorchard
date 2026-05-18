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

"""Pull request repository for GitHub PR tracking."""

import uuid
from datetime import datetime

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PRState, PullRequest
from app.models.tracked_repository import TrackedRepository
from app.repositories.base import BaseRepository


class PullRequestRepository(BaseRepository[PullRequest]):
    """Repository for pull requests, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository."""
        super().__init__(PullRequest, db, org_id=org_id)

    async def get_by_repo_and_number(
        self, repo_full_name: str, pr_number: int
    ) -> PullRequest | None:
        """Look up a PR by ``(repo_full_name, github_pr_number)`` within the org."""
        stmt = self._scoped(
            select(PullRequest)
            .where(
                PullRequest.github_pr_number == pr_number,
                PullRequest.github_repo_full_name == repo_full_name,
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def map_shas_to_bud_ids(self, shas: list[str]) -> dict[str, uuid.UUID]:
        """For each SHA in ``shas`` that matches a PR's ``merge_commit_sha``
        with a non-null ``bud_id``, return ``sha -> bud_id``.
        """
        if not shas:
            return {}
        stmt = self._scoped(
            select(PullRequest.merge_commit_sha, PullRequest.bud_id).where(
                PullRequest.merge_commit_sha.in_(shas),
                PullRequest.bud_id.is_not(None),
            )
        )
        result = await self._db.execute(stmt)
        return {row[0]: row[1] for row in result.all() if row[0] and row[1]}

    async def map_shas_to_pr_meta(self, shas: list[str]) -> dict[str, tuple[int, str | None]]:
        """Resolve a batch of merge SHAs to ``(pr_number, html_url)`` tuples.

        Used by the Features API to surface the PR that soft-deleted a
        feature (``features.deactivated_at_sha``) — a single bulk lookup
        instead of one query per feature.

        SHAs with no matching PR are absent from the returned dict so
        the caller can render the bare commit SHA as a fallback.
        """
        if not shas:
            return {}
        stmt = self._scoped(
            select(
                PullRequest.merge_commit_sha,
                PullRequest.github_pr_number,
                PullRequest.html_url,
            ).where(
                PullRequest.merge_commit_sha.in_(shas),
                PullRequest.github_pr_number.is_not(None),
            )
        )
        result = await self._db.execute(stmt)
        return {row[0]: (row[1], row[2]) for row in result.all() if row[0] and row[1] is not None}

    async def count_opened_by_author_in_window(
        self, since: datetime, until: datetime
    ) -> dict[uuid.UUID, int]:
        """Count PRs opened per author with ``created_at`` in [since, until)."""
        stmt = self._scoped(
            select(PullRequest.author_user_id, func.count().label("cnt"))
            .where(
                PullRequest.created_at >= since,
                PullRequest.created_at < until,
                PullRequest.author_user_id.isnot(None),
            )
            .group_by(PullRequest.author_user_id)
        )
        result = await self._db.execute(stmt)
        return {row.author_user_id: row.cnt for row in result.all()}

    async def count_merged_by_author_in_window(
        self, since: datetime, until: datetime
    ) -> dict[uuid.UUID, int]:
        """Count PRs merged per author with ``merged_at`` in [since, until)."""
        stmt = self._scoped(
            select(PullRequest.author_user_id, func.count().label("cnt"))
            .where(
                PullRequest.state == PRState.MERGED,
                PullRequest.merged_at >= since,
                PullRequest.merged_at < until,
                PullRequest.author_user_id.isnot(None),
            )
            .group_by(PullRequest.author_user_id)
        )
        result = await self._db.execute(stmt)
        return {row.author_user_id: row.cnt for row in result.all()}

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

    async def list_open_for_bud_with_repo(
        self,
        bud_id: uuid.UUID,
        *,
        impacted_repo_ids: list[uuid.UUID] | None = None,
    ) -> list[tuple[PullRequest, TrackedRepository | None]]:
        """List open PRs for a BUD joined with their tracked repository.

        When ``impacted_repo_ids`` is provided, the result includes any open
        PR that is either linked to ``bud_id`` directly OR targets one of
        the impacted repos. Used by release-stage views that need to surface
        open PRs in repos affected by the BUD even if the PR forgot to set
        a ``bud_id``.

        Args:
            bud_id: The BUD UUID to filter on.
            impacted_repo_ids: Additional repo UUIDs to include open PRs for.

        Returns:
            List of ``(PullRequest, TrackedRepository | None)`` tuples.
        """
        filters = [PullRequest.bud_id == bud_id]
        if impacted_repo_ids:
            filters.append(PullRequest.repo_id.in_(impacted_repo_ids))

        stmt = self._scoped(
            select(PullRequest, TrackedRepository)
            .join(
                TrackedRepository,
                PullRequest.repo_id == TrackedRepository.id,
                isouter=True,
            )
            .where(
                PullRequest.state == PRState.OPEN,
                or_(*filters),
            )
        )
        result = await self._db.execute(stmt)
        return list(result.tuples().all())

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
