# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Developer activity log model for tracking all Claude Code events.

Unified table for all activity types: session lifecycle, commits,
file changes, tool errors, API errors, and activity summaries.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DevActivityLog(BaseModel):
    """Unified developer activity log for all Claude Code hook events.

    Stores session starts/ends, commits, file changes, tool errors,
    API errors, and activity summaries in a single table. BUD and repo
    links are nullable — not all activity is tied to a BUD or tracked repo.
    """

    __tablename__ = "dev_activity_logs"
    __table_args__ = (
        Index("ix_dev_activity_bud_id", "bud_id"),
        Index("ix_dev_activity_org_created", "org_id", "created_at"),
        Index("ix_dev_activity_session_id", "session_id"),
        Index("ix_dev_activity_repo_id", "repo_id"),
        Index("ix_dev_activity_event_type", "event_type"),
        Index(
            "ix_dev_activity_commit_sha",
            "org_id",
            "commit_sha",
            postgresql_where=text("commit_sha IS NOT NULL"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    bud_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    branch: Mapped[str | None] = mapped_column(String(500), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    file_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    files_changed: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Raw filesystem path of the repo this activity came from. Persisted even
    # when repo_id is NULL (i.e. the path doesn't match any tracked_repository),
    # so the BUD testing tab can group "untracked" rows by path and offer an
    # "Add as tracked" CTA. Backfilled to NULL for existing rows.
    repo_path: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<DevActivityLog(event_type={self.event_type!r}, "
            f"bud_id={self.bud_id}, session_id={self.session_id!r})>"
        )
