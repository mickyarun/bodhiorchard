"""BUD (Business Understanding Document) model."""

import uuid
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel


class BUDTimelineEventType(StrEnum):
    """Types of events recorded in a BUD's activity timeline."""

    CREATED = "created"
    REQUESTED = "requested"
    APPROVED = "approved"
    STATUS_CHANGE = "status_change"
    ASSIGNED = "assigned"
    UNASSIGNED = "unassigned"
    AI_AGENT_STARTED = "ai_agent_started"
    AI_AGENT_COMPLETED = "ai_agent_completed"
    AI_AGENT_FAILED = "ai_agent_failed"
    CONTENT_UPDATED = "content_updated"
    DESIGN_GENERATED = "design_generated"
    COMMENT = "comment"
    TECH_ARCH_STARTED = "tech_arch_started"
    TECH_ARCH_APPROVED = "tech_arch_approved"
    TECH_ARCH_REJECTED = "tech_arch_rejected"
    REASSIGNMENT_REQUESTED = "reassignment_requested"


class BUDStatus(StrEnum):
    """Lifecycle stage of a BUD document."""

    BUD = "bud"
    DESIGN = "design"
    TECH_ARCH = "tech_arch"
    DEVELOPMENT = "development"
    CODE_REVIEW = "code_review"
    TESTING = "testing"
    UAT = "uat"
    PROD = "prod"
    CLOSED = "closed"
    DISCARDED = "discarded"


class BUDDocument(BaseModel):
    """Business Understanding Document with embedded vector representation."""

    __tablename__ = "bud_documents"
    __table_args__ = (
        UniqueConstraint("org_id", "bud_number", name="uq_bud_org_number"),
        Index("ix_bud_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    bud_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[BUDStatus] = mapped_column(
        Enum(BUDStatus, name="bud_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=BUDStatus.BUD,
    )
    requirements_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_spec_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_plan_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(384), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    assignee = relationship("User", foreign_keys=[assignee_id], lazy="joined")
    designs: Mapped[list["BUDDesign"]] = relationship(
        back_populates="bud", cascade="all, delete-orphan", lazy="selectin"
    )
    timeline_events: Mapped[list["BUDTimelineEvent"]] = relationship(
        back_populates="bud", cascade="all, delete-orphan", lazy="noload"
    )
    agent_tasks: Mapped[list["BUDAgentTask"]] = relationship(
        back_populates="bud", cascade="all, delete-orphan", lazy="noload"
    )

    def __repr__(self) -> str:
        return f"<BUDDocument(id={self.id}, bud_number={self.bud_number})>"


class BUDDesignStatus(StrEnum):
    """Status of a single design wireframe."""

    PENDING = "pending"
    GENERATING = "generating"
    READY = "ready"
    FAILED = "failed"


class BUDDesign(BaseModel):
    """Per-repo design wireframe for a BUD document."""

    __tablename__ = "bud_designs"
    __table_args__ = (
        UniqueConstraint("bud_id", "repo_id", name="uq_bud_design_bud_repo"),
        Index("ix_bud_designs_bud_id", "bud_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bud_documents.id", ondelete="CASCADE"), nullable=False
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracked_repositories.id"), nullable=True
    )
    design_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    design_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[BUDDesignStatus] = mapped_column(
        String(20), nullable=False, default=BUDDesignStatus.PENDING
    )
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

    bud: Mapped["BUDDocument"] = relationship(back_populates="designs")

    def __repr__(self) -> str:
        return f"<BUDDesign(id={self.id}, bud_id={self.bud_id}, repo_id={self.repo_id})>"


class BUDChatMessage(BaseModel):
    """Persisted chat message for a BUD section (phase/design scoped)."""

    __tablename__ = "bud_chat_messages"
    __table_args__ = (Index("ix_bud_chat_bud_section", "bud_id", "section"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    section: Mapped[str] = mapped_column(String(30), nullable=False)
    design_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_designs.id", ondelete="SET NULL"),
        nullable=True,
    )
    role: Mapped[str] = mapped_column(String(10), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    user = relationship("User", lazy="joined")

    def __repr__(self) -> str:
        return f"<BUDChatMessage(id={self.id}, bud_id={self.bud_id}, role={self.role})>"


class BUDTimelineEvent(BaseModel):
    """Single event in a BUD's activity timeline."""

    __tablename__ = "bud_timeline_events"
    __table_args__ = (Index("ix_bud_timeline_bud_id", "bud_id"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    event_type: Mapped[str] = mapped_column(String(30), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    detail: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    bud: Mapped["BUDDocument"] = relationship(back_populates="timeline_events")

    def __repr__(self) -> str:
        return f"<BUDTimelineEvent(id={self.id}, bud_id={self.bud_id}, type={self.event_type})>"
