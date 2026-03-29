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


class RepoStatus(StrEnum):
    """Lifecycle status of a tracked repository."""

    ACTIVE = "active"
    IGNORED = "ignored"
    REMOVED = "removed"


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
    github_repo_full_name: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True,
    )

    def __repr__(self) -> str:
        return f"<TrackedRepository(name={self.name!r}, status={self.status})>"
