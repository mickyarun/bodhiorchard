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

from sqlalchemy import and_, func, or_, select
from sqlalchemy import update as sql_update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PRState, PullRequest
from app.models.tracked_repository import TrackedRepository
from app.repositories.base import BaseRepository, rowcount


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

    async def repoint_author(self, source_user_id: uuid.UUID, target_user_id: uuid.UUID) -> int:
        """Re-attribute every PR authored by the source user to the target.

        Called from member-merge. Without this the merged-away stub keeps
        every PR it ingested, so contributor breakdowns, per-person
        throughput and capacity views all report zero for the surviving
        member while the deactivated row holds the real history.

        Returns:
            The number of pull requests re-pointed.
        """
        result = await self._db.execute(
            sql_update(PullRequest)
            .where(
                PullRequest.author_user_id == source_user_id,
                PullRequest.org_id == self._org_id,
            )
            .values(author_user_id=target_user_id)
        )
        return rowcount(result)

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

    async def get_distinct_author_user_ids_for_bud(self, bud_id: uuid.UUID) -> set[uuid.UUID]:
        """Distinct author user_ids across every PR linked to the BUD.

        Used by the stage-promotion XP split — anyone who opened a PR
        against the BUD's work counts as a contributor, regardless of
        whether the PR has merged yet. Rows with NULL ``author_user_id``
        (PRs opened by users not mapped to a bodhi account) are excluded.
        """
        stmt = self._scoped(
            select(PullRequest.author_user_id).where(
                PullRequest.bud_id == bud_id,
                PullRequest.author_user_id.is_not(None),
            )
        ).distinct()
        result = await self._db.execute(stmt)
        return {uid for (uid,) in result.all() if uid is not None}

    async def list_for_bud(self, bud_id: uuid.UUID) -> list[PullRequest]:
        """List all PRs linked to a BUD, newest first."""
        stmt = self._scoped(
            select(PullRequest)
            .where(PullRequest.bud_id == bud_id)
            .order_by(PullRequest.created_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def has_merged_for_bud(self, bud_id: uuid.UUID) -> bool:
        """True if the BUD has at least one merged PR.

        Used by the estimator as a strong "the code work is done" signal for
        the development / code_review phases — independent of whether todos
        were ticked off.
        """
        stmt = self._scoped(
            select(func.count(PullRequest.id)).where(
                PullRequest.bud_id == bud_id,
                PullRequest.state == PRState.MERGED,
            )
        )
        return int((await self._db.execute(stmt)).scalar_one()) > 0

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

        Three-way predicate so the release-stage views (UAT / PROD tabs)
        only surface PRs that genuinely relate to ``bud_id``:

        * ``bud_id == X`` — the PR is directly linked to this BUD.
        * ``bud_id IS NULL AND repo_id IN impacted_repo_ids`` — aggregate
          release PRs like ``develop → main`` legitimately carry no single
          owning BUD; we keep them visible on the impacted repo's stage tab
          because the SHA-walk in the release detector uses them to attribute
          merges back to multiple BUDs.

        A plain ``OR(bud_id == X, repo_id IN impacted)`` would also let
        through PRs linked to a **different** BUD that happens to touch the
        same impacted repo — which is the over-matching bug this method now
        prevents.

        Args:
            bud_id: The BUD UUID to filter on.
            impacted_repo_ids: Repo UUIDs whose unlinked release PRs should
                stay visible. When ``None`` / empty, only directly-linked
                PRs are returned.

        Returns:
            List of ``(PullRequest, TrackedRepository | None)`` tuples.
        """
        if impacted_repo_ids:
            bud_predicate = or_(
                PullRequest.bud_id == bud_id,
                and_(
                    PullRequest.bud_id.is_(None),
                    PullRequest.repo_id.in_(impacted_repo_ids),
                ),
            )
        else:
            bud_predicate = PullRequest.bud_id == bud_id

        stmt = self._scoped(
            select(PullRequest, TrackedRepository)
            .join(
                TrackedRepository,
                PullRequest.repo_id == TrackedRepository.id,
                isouter=True,
            )
            .where(
                PullRequest.state == PRState.OPEN,
                bud_predicate,
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
