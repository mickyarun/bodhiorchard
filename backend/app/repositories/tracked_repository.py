"""Tracked repository data access repository."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.repositories.base import BaseRepository


class TrackedRepoRepository(BaseRepository[TrackedRepository]):
    """Repository for TrackedRepository, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries.
        """
        super().__init__(TrackedRepository, db, org_id=org_id)

    async def list_active(self) -> list[TrackedRepository]:
        """List repos with status=active, ordered by name.

        Returns:
            List of active TrackedRepository instances.
        """
        result = await self._db.execute(
            self._scoped(
                select(TrackedRepository).where(TrackedRepository.status == RepoStatus.ACTIVE)
            ).order_by(TrackedRepository.name)
        )
        return list(result.scalars().all())

    async def list_visible(self) -> list[TrackedRepository]:
        """List repos with status != removed, ordered by name.

        Returns:
            List of active and ignored TrackedRepository instances.
        """
        result = await self._db.execute(
            self._scoped(
                select(TrackedRepository).where(TrackedRepository.status != RepoStatus.REMOVED)
            ).order_by(TrackedRepository.name)
        )
        return list(result.scalars().all())

    async def get_by_name(self, name: str) -> TrackedRepository | None:
        """Lookup a repo by name within the org.

        Args:
            name: Repository directory name.

        Returns:
            TrackedRepository or None.
        """
        result = await self._db.execute(
            self._scoped(select(TrackedRepository).where(TrackedRepository.name == name))
        )
        return result.scalar_one_or_none()

    async def get_by_path(self, path: str) -> TrackedRepository | None:
        """Lookup a repo by exact path.

        Args:
            path: Absolute filesystem path.

        Returns:
            TrackedRepository or None.
        """
        result = await self._db.execute(
            self._scoped(select(TrackedRepository).where(TrackedRepository.path == path))
        )
        return result.scalar_one_or_none()

    async def upsert(self, path: str, name: str) -> TrackedRepository:
        """Insert a new repo or re-activate if previously removed/ignored.

        Args:
            path: Absolute filesystem path.
            name: Repository directory name.

        Returns:
            The upserted TrackedRepository.
        """
        existing = await self.get_by_path(path)
        if existing:
            existing.status = RepoStatus.ACTIVE
            existing.name = name
            await self._db.flush()
            return existing

        repo = TrackedRepository(
            org_id=self._org_id,
            path=path,
            name=name,
            status=RepoStatus.ACTIVE,
        )
        self._db.add(repo)
        await self._db.flush()
        return repo

    async def set_status(
        self, repo_id: uuid.UUID, new_status: RepoStatus
    ) -> TrackedRepository | None:
        """Change a repo's status.

        Args:
            repo_id: The repository UUID.
            new_status: New status value.

        Returns:
            Updated TrackedRepository or None if not found.
        """
        repo = await self.get_by_id(repo_id)
        if repo and repo.org_id == self._org_id:
            repo.status = new_status
            await self._db.flush()
            return repo
        return None

    async def update_after_scan(
        self,
        repo_path: str,
        head_sha: str,
        knowledge_count: int,
        feature_count: int,
    ) -> None:
        """Update SHA, timestamp, and counters after a scan.

        Args:
            repo_path: Path to identify the repo.
            head_sha: New HEAD SHA.
            knowledge_count: Number of knowledge items.
            feature_count: Number of feature items.
        """
        await self._db.execute(
            update(TrackedRepository)
            .where(
                TrackedRepository.org_id == self._org_id,
                TrackedRepository.path == repo_path,
            )
            .values(
                head_sha=head_sha,
                last_scanned_at=datetime.now(UTC),
                knowledge_count=knowledge_count,
                feature_count=feature_count,
            )
        )

    async def get_active_paths(self) -> list[str]:
        """Return paths of active repos.

        Returns:
            List of absolute path strings.
        """
        result = await self._db.execute(
            self._scoped(
                select(TrackedRepository.path).where(TrackedRepository.status == RepoStatus.ACTIVE)
            )
        )
        return list(result.scalars().all())

    async def get_active_path_name_pairs(self) -> list[tuple[str, str]]:
        """Return (path, name) pairs of active repos.

        Returns:
            List of (path, name) tuples.
        """
        result = await self._db.execute(
            self._scoped(
                select(TrackedRepository.path, TrackedRepository.name).where(
                    TrackedRepository.status == RepoStatus.ACTIVE
                )
            ).order_by(TrackedRepository.name)
        )
        return list(result.all())

    async def get_paths_by_ids(self, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Batch-resolve repo IDs to filesystem paths.

        Args:
            ids: Set of repository UUIDs.

        Returns:
            Dict mapping repo UUID → path string.
        """
        if not ids:
            return {}
        result = await self._db.execute(
            select(TrackedRepository.id, TrackedRepository.path).where(
                TrackedRepository.id.in_(ids)
            )
        )
        return {row.id: row.path for row in result.all()}

    async def get_active_id_path_name(
        self,
    ) -> list[tuple[uuid.UUID, str, str]]:
        """Return (id, path, name) triples of active repos.

        Returns:
            List of (id, path, name) tuples.
        """
        result = await self._db.execute(
            self._scoped(
                select(
                    TrackedRepository.id,
                    TrackedRepository.path,
                    TrackedRepository.name,
                ).where(TrackedRepository.status == RepoStatus.ACTIVE)
            ).order_by(TrackedRepository.name)
        )
        return list(result.all())

    async def get_by_github_full_name(
        self, full_name: str,
    ) -> TrackedRepository | None:
        """Look up a repo by GitHub full name (owner/repo).

        Uses org scope if set, otherwise searches across all orgs
        (used by webhook handler to resolve org from repo name).
        """
        stmt = self._scoped(
            select(TrackedRepository).where(
                TrackedRepository.github_repo_full_name == full_name,
            )
        ).limit(1)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
