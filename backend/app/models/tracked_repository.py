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

"""Tracked repository model for explicit repo management."""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.repo_layer import RepoLayer


class RepoStatus(StrEnum):
    """Lifecycle status of a tracked repository."""

    ACTIVE = "active"
    IGNORED = "ignored"
    REMOVED = "removed"


class SetupPrState(StrEnum):
    """Lifecycle state of the Bodhiorchard MCP setup PR for a repo.

    ``OPEN`` is written when the PR is created (or adopted from a
    pre-existing branch). The webhook flips it to ``MERGED`` or
    ``CLOSED`` on ``pull_request.closed``. ``None`` (column NULL) means
    "no setup PR has been opened" — either the GitHub App isn't
    configured (manual fallback) or the setup phase has not yet run.
    """

    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class TrackedRepository(BaseModel):
    """A git repository tracked by an organization."""

    __tablename__ = "tracked_repositories"
    __table_args__ = (
        UniqueConstraint("org_id", "path", name="uq_tracked_repo_org_path"),
        Index("ix_tracked_repo_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    path: Mapped[str] = mapped_column(String(1000), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RepoStatus] = mapped_column(
        Enum(
            RepoStatus,
            name="repo_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=RepoStatus.ACTIVE,
    )
    head_sha: Mapped[str | None] = mapped_column(String(40), nullable=True)
    last_scanned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    knowledge_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    feature_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    main_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    develop_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    # Optional UAT branch (e.g. "release/uat"). When set AND the org has
    # bud_stages.uat_enabled=true, PR merges into this branch trigger
    # release-stage detection that records merged_to_uat events on every
    # BUD whose commits are included.
    uat_branch: Mapped[str | None] = mapped_column(String(100), nullable=True)
    github_repo_full_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )

    # MCP-setup PR tracking. ``setup_branch_pushed_at`` is written every
    # time the per-repo setup phase successfully pushes the
    # ``bodhiorchard/init-setup`` branch. ``setup_pr_*`` are written when
    # the GitHub App opens (or adopts) the PR for that branch; null when
    # the App isn't configured for the org and the user must open the PR
    # manually. The webhook flips ``setup_pr_state`` on
    # ``pull_request.closed``.
    setup_branch_pushed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    setup_pr_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    setup_pr_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    setup_pr_state: Mapped[SetupPrState | None] = mapped_column(
        Enum(
            SetupPrState,
            name="tracked_repo_setup_pr_state",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
    )

    # Architectural classification produced by the ``classify_repo`` stage
    # (see ``app/services/scan/repo_classify``). Null until the first
    # post-ingest classify run. ``backend_link`` reads ``repo_layer`` to
    # decide whether a repo participates as an index target (BACKEND) or
    # a frontend whose features should be linked (FRONTEND); other layers
    # are ignored.
    repo_layer: Mapped[RepoLayer | None] = mapped_column(
        Enum(
            RepoLayer,
            name="repo_layer",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=True,
        index=True,
    )
    tech_stack: Mapped[str | None] = mapped_column(String(50), nullable=True)
    db_flavor: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<TrackedRepository(name={self.name!r}, status={self.status})>"
