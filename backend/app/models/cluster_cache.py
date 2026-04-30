# SPDX-License-Identifier: MIT
# Copyright (C) 2026 Arun Rajkumar

"""Cache table for code-graph cluster → file mappings keyed on (repo, SHA).

The v2 ``extract`` stage feeds ``Community`` rows from the upstream code
indexer (``app.services.code_indexer`` — graphify-based) into reduction
stages. Persisting the post-cluster rows here, keyed on
``(repo_id, head_sha)``, lets a re-run on the same SHA hydrate the stage
output from Postgres in a single query. Rows are replaced wholesale on
cache rebuild, so stale rows for an old SHA simply linger until the
row's ``repo_id`` is dropped (CASCADE on tracked_repositories).

This table was previously called ``gitnexus_community_cache``; the rename
in alembic ``zv_cluster_cache_graphify`` shed the GitNexus name when the
project moved to graphify. Schema is otherwise identical apart from a
new ``symbols`` JSONB column for the ``code_impact`` MCP tools.
"""

import uuid
from typing import Any

from sqlalchemy import (
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ClusterCache(BaseModel):
    """One row per (repo, head_sha, cluster) — the cached extract output."""

    __tablename__ = "cluster_cache"
    __table_args__ = (
        # org_id leads the unique key so it matches the multi-tenant
        # convention used elsewhere in the schema, even though
        # ``tracked_repositories.id`` is globally unique. Adding it costs
        # one extra column in the index — same disk footprint, zero query
        # cost — and prevents the constraint from accidentally
        # cross-tenant if any future code path forgets the org filter.
        UniqueConstraint(
            "org_id",
            "repo_id",
            "head_sha",
            "cluster_id",
            name="uq_cc_repo_sha_cluster",
        ),
        Index("ix_cc_repo_sha", "repo_id", "head_sha"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    head_sha: Mapped[str] = mapped_column(String(40), nullable=False)
    cluster_id: Mapped[str] = mapped_column(String(255), nullable=False)
    label: Mapped[str] = mapped_column(String(500), nullable=False)
    heuristic_label: Mapped[str | None] = mapped_column(String(500), nullable=True)
    symbol_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cohesion: Mapped[float | None] = mapped_column(Float, nullable=True)
    files: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    symbols: Mapped[list[Any]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
