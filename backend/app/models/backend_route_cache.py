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

"""SHA-keyed cache of backend HTTP route declarations.

Written by the per-repo ``extract_routes`` stage on cache miss; read by
the global ``backend_link`` phase to assemble its in-memory
:class:`BackendIndex` without re-walking every backend's worktree on
every scan.

Same shape as :class:`ClusterCache` and :class:`RepoGraphCache` —
``(org_id, repo_id, head_sha)`` is the cache key, with the route's
identity columns appended to the unique constraint so a single repo /
SHA can hold many rows. New commits land under a fresh ``head_sha``;
old SHAs stay until the repo is dropped (CASCADE on
``tracked_repositories``).
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class BackendRouteCache(BaseModel):
    """One row per declared HTTP route at a given (repo, head_sha)."""

    __tablename__ = "backend_route_cache"
    __table_args__ = (
        # org_id leads for multi-tenant safety — same rationale as
        # ``cluster_cache.uq_cc_repo_sha_cluster``.
        UniqueConstraint(
            "org_id",
            "repo_id",
            "head_sha",
            "normalised_path",
            "http_method",
            "file_path",
            name="uq_brc_repo_sha_route",
        ),
        Index("ix_brc_repo_sha", "repo_id", "head_sha"),
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
    # Normalised to ``/segment/:param/...`` so it lines up with the
    # frontend extractor's path shape — JOINs against
    # ``feature_to_repo.api_paths`` are exact-string comparisons.
    normalised_path: Mapped[str] = mapped_column(String(500), nullable=False)
    http_method: Mapped[str] = mapped_column(String(20), nullable=False)
    file_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    indexed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<BackendRouteCache(repo={self.repo_id}, sha={self.head_sha[:8]}, "
            f"{self.http_method.upper()} {self.normalised_path!r})>"
        )
