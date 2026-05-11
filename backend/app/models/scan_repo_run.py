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

"""ScanRepoRun — per-repo unit of work inside one scan.

A scan can target N repositories. We store one row here per
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
    """One repo's slice of a scan."""

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
