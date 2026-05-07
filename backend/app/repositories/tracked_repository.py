# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tracked repository data access repository."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repo_layer import RepoLayer
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.repositories.base import BaseRepository


class TrackedRepoRepository(BaseRepository[TrackedRepository]):
    """Repository for TrackedRepository, scoped to an organization."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID | None = None) -> None:
        """Initialize the repository.

        Args:
            db: Async SQLAlchemy session.
            org_id: Organization UUID for scoping queries. If ``None``,
                queries are unscoped — only valid for cross-org lookups
                (e.g. resolving the org for an inbound webhook).
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

    async def list_all_ordered_by_name(self) -> list[TrackedRepository]:
        """List every repo in the org, including archived/removed.

        Used by the scan-page selection grid which needs to show every
        tracked repo regardless of status so the user can spot ones in
        unexpected states (e.g. removed by accident).
        """
        result = await self._db.execute(
            self._scoped(select(TrackedRepository)).order_by(TrackedRepository.name)
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

    async def reset_head_shas(self) -> int:
        """Clear ``head_sha`` + ``last_scanned_at`` on every active repo.

        Called by the legacy ``POST /scan`` endpoint when ``full_rescan``
        is True so the next scan treats each repo as a first-time index —
        the SHA-diff in ``phase_a_scan_mode`` sees no prior SHA and forces
        a full rebuild.

        Returns:
            Number of rows updated.
        """
        result = await self._db.execute(
            update(TrackedRepository)
            .where(
                TrackedRepository.org_id == self._org_id,
                TrackedRepository.status == RepoStatus.ACTIVE,
            )
            .values(head_sha=None, last_scanned_at=None)
        )
        return result.rowcount

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

    async def upsert_for_github_repo(
        self,
        *,
        github_full_name: str,
        path: str,
        name: str,
    ) -> TrackedRepository:
        """Upsert keyed on ``github_repo_full_name`` first, then on ``path``.

        The same GitHub repo can be onboarded twice for an org — once via
        "Local folder" pointing at the user's working checkout, once via
        the GitHub-App bulk-import which clones into ``repoclone/...``.
        Different paths, same logical repo. Path-keyed :meth:`upsert`
        treats them as distinct rows and the scan pipeline ends up running
        synthesis once per row. This adoption helper claims the existing
        row when the GitHub full name already matches an active/ignored
        entry in the org and updates its path to the freshly-cloned tree.
        Falls back to path-keyed upsert when the full name is new.
        """
        existing = await self.get_by_github_full_name(github_full_name)
        if existing is not None and existing.status != RepoStatus.REMOVED:
            existing.path = path
            existing.name = name
            existing.status = RepoStatus.ACTIVE
            await self._db.flush()
            return existing
        return await self.upsert(path, name)

    async def set_onboard_metadata(
        self,
        repo: TrackedRepository,
        *,
        github_full_name: str,
        main_branch: str,
        develop_branch: str | None,
        uat_branch: str | None,
    ) -> TrackedRepository:
        """Persist the GitHub full name + chosen branches on a freshly upserted repo.

        Used by the bulk-onboard job after :meth:`upsert` so the handler
        never has to mutate ORM attributes itself. Idempotent — overwrites
        whatever was stored. Flushes + refreshes so subsequent attribute
        reads stay inside the async greenlet.
        """
        repo.github_repo_full_name = github_full_name
        repo.main_branch = main_branch
        repo.develop_branch = develop_branch
        repo.uat_branch = uat_branch or None
        await self._db.flush()
        await self._db.refresh(repo)
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

    async def set_classification(
        self,
        repo_id: uuid.UUID,
        *,
        layer: RepoLayer,
        tech_stack: str | None,
        db_flavor: str | None,
    ) -> None:
        """Persist the per-repo classification produced by ``classify_repo``.

        Idempotent — overwrites whatever was there. The classifier is
        cheap to re-run on every scan so we don't need a "first write
        wins" guard. ``org_id`` scope is enforced via the ``WHERE``
        clause to avoid cross-org writes.
        """
        await self._db.execute(
            update(TrackedRepository)
            .where(
                TrackedRepository.org_id == self._org_id,
                TrackedRepository.id == repo_id,
            )
            .values(
                repo_layer=layer,
                tech_stack=tech_stack,
                db_flavor=db_flavor,
            )
        )

    async def list_by_layer(self, layer: RepoLayer) -> list[TrackedRepository]:
        """All active repos in the org with the given ``repo_layer``.

        Used by ``backend_link`` to find every BACKEND repo whose worktree
        should be indexed for route extraction.
        """
        result = await self._db.execute(
            self._scoped(
                select(TrackedRepository).where(
                    TrackedRepository.repo_layer == layer,
                    TrackedRepository.status == RepoStatus.ACTIVE,
                )
            ).order_by(TrackedRepository.name)
        )
        return list(result.scalars().all())

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

    async def get_names_by_ids(self, ids: list[uuid.UUID]) -> dict[uuid.UUID, str]:
        """Batch-resolve repo IDs to display names.

        Used by scan-result serializers to attach repo names to lists
        of ``ScanRepoRun`` rows in a single round-trip.
        """
        if not ids:
            return {}
        result = await self._db.execute(
            self._scoped(
                select(TrackedRepository.id, TrackedRepository.name).where(
                    TrackedRepository.id.in_(ids)
                )
            )
        )
        return {row.id: row.name for row in result.all()}

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

    async def get_name_by_id(self, repo_id: uuid.UUID) -> str | None:
        """Return only the ``name`` column for a tracked repo, or None."""
        stmt = self._scoped(select(TrackedRepository.name).where(TrackedRepository.id == repo_id))
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_full_names_by_org(self) -> set[str]:
        """Return the set of non-null ``github_repo_full_name`` values for the org.

        Used by the bulk-import picker to mark which installable repos are
        already tracked. Excludes ``REMOVED`` rows so a soft-deleted repo
        appears re-importable on the picker — without this filter, the
        checkbox stays disabled with an "already tracked" badge after a
        delete and the user can never re-add the repo.
        """
        stmt = self._scoped(
            select(TrackedRepository.github_repo_full_name).where(
                TrackedRepository.github_repo_full_name.isnot(None),
                TrackedRepository.status != RepoStatus.REMOVED,
            )
        )
        result = await self._db.execute(stmt)
        return {row for row in result.scalars().all() if row is not None}

    async def get_by_github_full_name(
        self,
        full_name: str,
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
