"""PRD (Product Requirements Document) model."""

import uuid
from enum import StrEnum

from pgvector.sqlalchemy import Vector
from sqlalchemy import Enum, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class PRDStatus(StrEnum):
    """Lifecycle status of a PRD document."""

    DRAFT = "draft"
    DESIGN = "design"
    TECH_SPEC = "tech-spec"
    IN_DEV = "in-dev"
    IN_QA = "in-qa"
    IN_UAT = "in-uat"
    DEPLOYED = "deployed"
    CANCELLED = "cancelled"


class PRDDocument(BaseModel):
    """Product Requirements Document with embedded vector representation."""

    __tablename__ = "prd_documents"
    __table_args__ = (
        UniqueConstraint("org_id", "prd_number", name="uq_prd_org_number"),
        Index("ix_prd_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    prd_number: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[PRDStatus] = mapped_column(
        Enum(PRDStatus, name="prd_status", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=PRDStatus.DRAFT,
    )
    content_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    tech_spec_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_plan_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(768), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<PRDDocument(id={self.id}, prd_number={self.prd_number})>"
