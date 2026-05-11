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

"""Cache table for the per-repo NetworkX call graph keyed on (repo, SHA).

The graph is produced by the code indexer (``app.services.code_indexer``)
during scan ingest and consumed by the ``code_impact`` / ``code_query``
/ ``code_context`` MCP tools to answer "what calls this?" / "what would
break if I change X?" questions without re-running tree-sitter.

Storage format is gzipped JSON node-link (NetworkX standard via
``networkx.readwrite.json_graph.node_link_data``). JSON-only on the
wire; never deserialised through formats that allow arbitrary code
execution on read.

One row per (repo, head_sha) pair — the cluster-level metadata lives in
``cluster_cache``.
"""

import uuid

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class RepoGraphCache(BaseModel):
    """One row per (repo, head_sha) holding the gzipped graph JSON."""

    __tablename__ = "repo_graph_cache"
    __table_args__ = (
        # org_id leads the unique key for multi-tenant consistency. See
        # the matching note on ClusterCache for rationale.
        UniqueConstraint(
            "org_id",
            "repo_id",
            "head_sha",
            name="uq_repo_graph_cache_repo_sha",
        ),
        Index("ix_repo_graph_cache_repo_sha", "repo_id", "head_sha"),
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
    graph_json: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    node_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    edge_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    computed_at: Mapped["DateTime"] = mapped_column(  # type: ignore[type-arg]
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
