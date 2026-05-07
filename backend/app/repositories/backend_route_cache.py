# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Repository for the ``backend_route_cache`` table.

Mirrors :class:`ClusterCacheRepository` — same SHA-keyed cache pattern,
delete-then-bulk-insert on miss, idempotent on the same SHA via the
unique constraint. Two reader methods serve the global linker
(``list_for_repo_sha``) and the cache-hit predicate
(``has_rows_for_sha``).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable

from sqlalchemy import delete, exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.backend_route_cache import BackendRouteCache
from app.repositories.base import BaseRepository
from app.services.scan.backend_link import RouteRecord


class BackendRouteCacheRepository(BaseRepository[BackendRouteCache]):
    """Org-scoped reads/writes for cached backend HTTP routes."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        super().__init__(BackendRouteCache, db, org_id=org_id)

    async def has_rows_for_sha(self, *, repo_id: uuid.UUID, head_sha: str) -> bool:
        """Cheap exists-check used by the ``extract_routes`` cache-hit gate.

        ``EXISTS`` short-circuits on the first matching row — this is the
        per-stage hot path so cache hits should resolve in microseconds.
        """
        stmt = self._scoped(
            select(
                exists().where(
                    BackendRouteCache.repo_id == repo_id,
                    BackendRouteCache.head_sha == head_sha,
                )
            )
        )
        return bool((await self._db.execute(stmt)).scalar())

    async def list_for_repo_sha(
        self, *, repo_id: uuid.UUID, head_sha: str
    ) -> list[BackendRouteCache]:
        """Return all cached routes for ``(repo, sha)`` — ordered for stable hashing."""
        stmt = self._scoped(
            select(BackendRouteCache).where(
                BackendRouteCache.repo_id == repo_id,
                BackendRouteCache.head_sha == head_sha,
            )
        ).order_by(
            BackendRouteCache.normalised_path,
            BackendRouteCache.http_method,
            BackendRouteCache.file_path,
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def replace_for_repo_sha(
        self,
        *,
        repo_id: uuid.UUID,
        head_sha: str,
        records: Iterable[RouteRecord],
    ) -> int:
        """Replace cached routes for ``(repo, sha)`` wholesale.

        Deletes the existing rows for this exact pair, then bulk-inserts
        the fresh set. Same atomic-within-transaction guarantee as the
        ClusterCache cousin. Duplicate ``RouteRecord``s in the input are
        de-duplicated by the unique constraint — last-wins semantics in
        practice.
        """
        assert self._org_id is not None, "org_id required for writes"
        await self._db.execute(
            delete(BackendRouteCache).where(
                BackendRouteCache.org_id == self._org_id,
                BackendRouteCache.repo_id == repo_id,
                BackendRouteCache.head_sha == head_sha,
            )
        )
        # ``set`` deduplicates structurally identical records before the
        # bulk insert so the unique constraint never fires within one
        # call. Worktrees that declare the same route twice in the same
        # file (e.g. a Flask ``@app.route`` with multiple methods) are
        # handled because each (method, path, file) tuple is distinct.
        unique_records = {(r.normalised_path, r.http_method, r.file_path) for r in records}
        if not unique_records:
            await self._db.flush()
            return 0
        self._db.add_all(
            BackendRouteCache(
                org_id=self._org_id,
                repo_id=repo_id,
                head_sha=head_sha,
                normalised_path=path,
                http_method=method,
                file_path=file_path,
            )
            for path, method, file_path in unique_records
        )
        await self._db.flush()
        return len(unique_records)
