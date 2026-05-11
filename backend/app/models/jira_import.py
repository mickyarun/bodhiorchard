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

"""Jira import models for tracking import sessions and issue-to-BUD mappings.

Two tables support the Jira import pipeline:
- ``jira_import_sessions``: tracks each import run (config, progress, result)
- ``jira_issue_bud_map``: per-issue traceability from Jira key to BUD/Bug
"""

import uuid
from enum import StrEnum

from sqlalchemy import ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ImportStatus(StrEnum):
    """Lifecycle states for a Jira import session."""

    PENDING = "pending"
    DISCOVERING = "discovering"
    READY = "ready"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class MapStatus(StrEnum):
    """Status of an individual Jira issue in the import mapping."""

    PENDING = "pending"
    IMPORTED = "imported"
    CONSOLIDATED = "consolidated"
    SKIPPED = "skipped"
    DUPLICATE_CANDIDATE = "duplicate_candidate"
    REVIEW_NEEDED = "review_needed"
    MERGED = "merged"
    FAILED = "failed"


class JiraImportSession(BaseModel):
    """Tracks a single Jira project import run.

    Stores configuration (JQL, status mapping, consolidation mode),
    discovery results, progress checkpoints for resume, and the
    final reconciliation report.
    """

    __tablename__ = "jira_import_sessions"
    __table_args__ = (
        Index("ix_jira_import_org_status", "org_id", "status"),
        Index("ix_jira_import_org_project", "org_id", "jira_project_key"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    jira_project_key: Mapped[str] = mapped_column(String(20), nullable=False)
    jira_project_name: Mapped[str] = mapped_column(String(255), nullable=False)
    jira_site_id: Mapped[str] = mapped_column(String(255), nullable=False)

    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=ImportStatus.PENDING, server_default="pending"
    )

    # Import configuration: JQL filter, status mapping, consolidation mode, etc.
    config: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Discovery results: issue counts by type, statuses found, sample issues
    discovery_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    # Final reconciliation report (set on completion)
    result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Links to in-memory job queue for WebSocket progress tracking
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Progress tracking for resume after crash
    total_issues: Mapped[int | None] = mapped_column(Integer, nullable=True)
    processed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default="0"
    )
    last_processed_key: Mapped[str | None] = mapped_column(String(50), nullable=True)

    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )

    def __repr__(self) -> str:
        return (
            f"<JiraImportSession(id={self.id}, project={self.jira_project_key!r}, "
            f"status={self.status!r}, progress={self.processed_count}/{self.total_issues})>"
        )


class JiraIssueBudMap(BaseModel):
    """Maps a single Jira issue to its corresponding BUD or Bug record.

    Provides traceability (which Jira issue became which BUD),
    duplicate prevention (unique constraint on org + jira key),
    and reconciliation reporting (status per issue).
    """

    __tablename__ = "jira_issue_bud_map"
    __table_args__ = (
        UniqueConstraint("org_id", "jira_issue_key", name="uq_jira_issue_org"),
        Index("ix_jira_map_session", "import_session_id"),
        Index("ix_jira_map_bud", "bud_id"),
        Index("ix_jira_map_bug", "bug_id"),
        Index("ix_jira_map_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    import_session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("jira_import_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    jira_issue_key: Mapped[str] = mapped_column(String(50), nullable=False)
    jira_issue_id: Mapped[str] = mapped_column(String(50), nullable=False)
    jira_issue_type: Mapped[str] = mapped_column(String(50), nullable=False)

    bud_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bud_documents.id", ondelete="SET NULL"), nullable=True
    )
    bug_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bugs.id", ondelete="SET NULL"), nullable=True
    )

    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=MapStatus.PENDING, server_default="pending"
    )

    # For consolidated issues: which parent Jira key they were folded into
    consolidated_into: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Human-readable note (e.g., similarity score for dedup candidates)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Per-issue error message if this specific issue failed
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<JiraIssueBudMap(jira={self.jira_issue_key!r}, "
            f"status={self.status!r}, bud_id={self.bud_id})>"
        )
