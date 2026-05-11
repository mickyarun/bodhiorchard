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

# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Repository for ``repo_graph_cache`` — the per-repo NetworkX call graph.

The graph is gzipped JSON node-link bytes. Encoders/decoders live in
``app.services.code_indexer.serialize`` so callers don't need to know
the on-wire format.
"""

from __future__ import annotations

import uuid

import networkx as nx
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.repo_graph_cache import RepoGraphCache
from app.repositories.base import BaseRepository
from app.services.code_indexer.serialize import (
    graph_to_gzip_json,
    gzip_json_to_graph,
)


class RepoGraphCacheRepository(BaseRepository[RepoGraphCache]):
    """Org-scoped reads/writes for the per-repo cached call graph."""

    def __init__(self, db: AsyncSession, *, org_id: uuid.UUID) -> None:
        """Initialise with an async session and the org scope."""
        super().__init__(RepoGraphCache, db, org_id=org_id)

    async def get_for_sha(
        self,
        *,
        repo_id: uuid.UUID,
        head_sha: str,
    ) -> nx.Graph | None:
        """Return the cached graph for ``(repo, sha)`` or ``None``."""
        stmt = self._scoped(
            select(RepoGraphCache).where(
                RepoGraphCache.repo_id == repo_id,
                RepoGraphCache.head_sha == head_sha,
            )
        )
        row = (await self._db.execute(stmt)).scalar_one_or_none()
        if row is None:
            return None
        return gzip_json_to_graph(row.graph_json)

    async def upsert_for_sha(
        self,
        *,
        repo_id: uuid.UUID,
        head_sha: str,
        graph: nx.Graph,
    ) -> None:
        """Replace any existing graph for ``(repo, sha)`` with ``graph``.

        Uses ``INSERT … ON CONFLICT (org_id, repo_id, head_sha) DO UPDATE``
        so two concurrent writers for the same SHA don't trip the unique
        constraint — the later one wins, which matches the
        delete-then-insert intent.
        """
        assert self._org_id is not None, "org_id required for writes"
        blob = graph_to_gzip_json(graph)
        stmt = pg_insert(RepoGraphCache).values(
            org_id=self._org_id,
            repo_id=repo_id,
            head_sha=head_sha,
            graph_json=blob,
            node_count=graph.number_of_nodes(),
            edge_count=graph.number_of_edges(),
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_repo_graph_cache_repo_sha",
            set_={
                "graph_json": stmt.excluded.graph_json,
                "node_count": stmt.excluded.node_count,
                "edge_count": stmt.excluded.edge_count,
            },
        )
        await self._db.execute(stmt)
        await self._db.flush()
