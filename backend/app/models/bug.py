"""Bug tracking model."""

import uuid
from datetime import datetime
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class BugSeverity(StrEnum):
    """Severity level of a reported bug."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class BugStatus(StrEnum):
    """Lifecycle status of a bug."""

    OPEN = "open"
    IN_PROGRESS = "in-progress"
    RESOLVED = "resolved"
    CLOSED = "closed"
    BLOCKED = "blocked"


class Bug(BaseModel):
    """Bug report linked to an organization and optionally to a PRD."""

    __tablename__ = "bugs"
    __table_args__ = (Index("ix_bugs_org_status_created", "org_id", "status", "created_at"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    prd_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prd_documents.id"), nullable=True
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[BugSeverity] = mapped_column(
        Enum(BugSeverity, name="bug_severity", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=BugSeverity.MEDIUM,
    )
    status: Mapped[BugStatus] = mapped_column(
        Enum(BugStatus, name="bug_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=BugStatus.OPEN,
    )
    module: Mapped[str | None] = mapped_column(String(255), nullable=True)
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    linked_pr: Mapped[str | None] = mapped_column(String(500), nullable=True)
    embedding = mapped_column(Vector(768), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<Bug(id={self.id}, title={self.title!r})>"
