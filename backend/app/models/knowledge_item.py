"""Knowledge item model for organizational knowledge base."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import JSON, Boolean, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, BaseModel

FEATURE_STATUSES = {"planned", "in_progress", "implemented"}


class KnowledgeRepoLink(Base):
    """Many-to-many link between knowledge items and tracked repositories."""

    __tablename__ = "knowledge_to_repo"
    __table_args__ = (
        UniqueConstraint("knowledge_id", "repo_id", name="uq_krl_knowledge_repo"),
        Index("ix_krl_repo_id", "repo_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    knowledge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("knowledge_items.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="CASCADE"),
        nullable=False,
    )
    code_locations: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class KnowledgeItem(BaseModel):
    """A piece of organizational knowledge indexed for semantic retrieval."""

    __tablename__ = "knowledge_items"
    __table_args__ = (
        Index("ix_ki_org_cat_active", "org_id", "category", "is_active"),
        Index("ix_ki_org_cat_active_title", "org_id", "category", "is_active", "title"),
        Index("ix_ki_org_cat_active_source", "org_id", "category", "is_active", "source"),
        Index(
            "ix_ki_org_cat_active_fstatus",
            "org_id",
            "category",
            "is_active",
            "feature_status",
        ),
        Index("ix_ki_org_srcref_cat", "org_id", "source_ref", "category"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    source_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    tags: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    embedding = mapped_column(Vector(384), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    feature_status: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)

    repo_links: Mapped[list[KnowledgeRepoLink]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<KnowledgeItem(id={self.id}, title={self.title!r})>"
