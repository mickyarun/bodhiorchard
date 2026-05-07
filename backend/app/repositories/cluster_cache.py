# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Repository for the ``cluster_cache`` table.

Two operations:

- :meth:`list_for_repo_sha` — hydrate the entire cluster list for a
  ``(repo_id, head_sha)`` pair in one query. Returns ``[]`` on miss so
  the caller can fall through to a fresh index run.
- :meth:`replace_for_repo_sha` — wholesale replace the cached set for a
  pair: delete existing rows, bulk-insert new ones in one round-trip.
  Atomic because both run within the caller's transaction.

Renamed from ``GitnexusCommunityCacheRepository`` when bodhiorchard
moved to graphify; the column ``community_id`` is now ``cluster_id``
and rows additionally carry a ``symbols`` JSONB column.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cluster_cache import ClusterCache
from app.repositories.base import BaseRepository


class ClusterCacheRepository(BaseRepository[ClusterCache]):
    """Org-scoped reads/writes for cached extract-stage rows."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise with an async session and the org scope."""
        super().__init__(ClusterCache, db, org_id=org_id)

    async def list_for_repo_sha(
        self,
        *,
        repo_id: uuid.UUID,
        head_sha: str,
    ) -> list[ClusterCache]:
        """Return cached rows for a ``(repo, sha)`` pair, ordered symbol-desc."""
        stmt = self._scoped(
            select(ClusterCache).where(
                ClusterCache.repo_id == repo_id,
                ClusterCache.head_sha == head_sha,
            )
        ).order_by(ClusterCache.symbol_count.desc())
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def latest_head_sha(
        self,
        *,
        repo_id: uuid.UUID,
    ) -> str | None:
        """Return the most-recent head_sha cached for this repo, or ``None``."""
        stmt = self._scoped(
            select(ClusterCache.head_sha)
            .where(ClusterCache.repo_id == repo_id)
            .order_by(ClusterCache.updated_at.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def replace_for_repo_sha(
        self,
        *,
        repo_id: uuid.UUID,
        head_sha: str,
        rows: list[dict[str, Any]],
    ) -> int:
        """Replace cached rows for ``(repo, sha)`` with ``rows``.

        ``rows`` items must contain ``cluster_id``, ``label``,
        ``heuristic_label``, ``symbol_count``, ``cohesion``, ``files``,
        ``signature``, and may optionally contain ``symbols``. Returns
        the number of upserted rows.

        **Concurrency.** Two concurrent scans for the same
        ``(org_id, repo_id, head_sha)`` could both attempt this
        operation. We use ``INSERT … ON CONFLICT DO UPDATE`` instead
        of delete-then-insert so a colliding writer is "last write
        wins" rather than tripping the unique constraint.

        Stale rows for *removed* clusters (cluster_id present in the
        old set but absent in ``rows``) are pruned by an explicit DELETE
        before the upserts, scoped to cluster_ids not in the new set.
        """
        assert self._org_id is not None, "org_id required for writes"
        new_cluster_ids = {row["cluster_id"] for row in rows}

        # Prune cluster_ids that are no longer present.
        stale_filter = [
            ClusterCache.org_id == self._org_id,
            ClusterCache.repo_id == repo_id,
            ClusterCache.head_sha == head_sha,
        ]
        if new_cluster_ids:
            stale_filter.append(ClusterCache.cluster_id.notin_(new_cluster_ids))
        await self._db.execute(delete(ClusterCache).where(*stale_filter))

        if not rows:
            await self._db.flush()
            return 0

        # Upsert each surviving row by the unique key.
        for row in rows:
            stmt = pg_insert(ClusterCache).values(
                org_id=self._org_id,
                repo_id=repo_id,
                head_sha=head_sha,
                cluster_id=row["cluster_id"],
                label=row["label"],
                heuristic_label=row.get("heuristic_label"),
                symbol_count=int(row.get("symbol_count") or 0),
                cohesion=row.get("cohesion"),
                files=list(row.get("files") or []),
                symbols=list(row.get("symbols") or []),
                signature=row.get("signature") or "",
            )
            stmt = stmt.on_conflict_do_update(
                constraint="uq_cc_repo_sha_cluster",
                set_={
                    "label": stmt.excluded.label,
                    "heuristic_label": stmt.excluded.heuristic_label,
                    "symbol_count": stmt.excluded.symbol_count,
                    "cohesion": stmt.excluded.cohesion,
                    "files": stmt.excluded.files,
                    "symbols": stmt.excluded.symbols,
                    "signature": stmt.excluded.signature,
                },
            )
            await self._db.execute(stmt)
        await self._db.flush()
        return len(rows)
