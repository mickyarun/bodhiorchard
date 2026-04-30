# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""ScanRepoRun — per-repo unit of work inside one v2 scan.

A v2 scan can target N repositories. We store one row here per
(scan, repo) so the timeline UI knows which repos are queued/running/
done/failed/skipped, and so the resume path can find the unfinished
ones in O(1) per scan.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.scan_run_enums import RepoRunStatus


class ScanRepoRun(BaseModel):
    """One repo's slice of a v2 scan."""

    __tablename__ = "scan_repo_runs"
    __table_args__ = (
        UniqueConstraint("scan_id", "repo_id", name="uq_scan_repo_run_scan_repo"),
        Index("ix_scan_repo_run_scan_status", "scan_id", "status"),
        Index("ix_scan_repo_run_org_repo", "org_id", "repo_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    scan_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("scans.id", ondelete="CASCADE"),
        nullable=False,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    head_sha_at_start: Mapped[str | None] = mapped_column(String(40), nullable=True)
    status: Mapped[RepoRunStatus] = mapped_column(
        Enum(
            RepoRunStatus,
            name="repo_run_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=RepoRunStatus.QUEUED,
        server_default=RepoRunStatus.QUEUED.value,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    feature_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    skill_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<ScanRepoRun(scan={self.scan_id}, repo={self.repo_id}, status={self.status})>"
