"""Feature learning model for retrospective analysis and estimation improvement."""

import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class FeatureLearning(BaseModel):
    """Captures learnings from completed features to improve future estimates."""

    __tablename__ = "feature_learnings"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    prd_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("prd_documents.id"), nullable=False
    )
    cycle_time_days: Mapped[float | None] = mapped_column(
        Numeric(precision=8, scale=2), nullable=True
    )
    estimated_days: Mapped[float | None] = mapped_column(
        Numeric(precision=8, scale=2), nullable=True
    )
    bug_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retrospective_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding = mapped_column(Vector(768), nullable=True)

    def __repr__(self) -> str:
        return f"<FeatureLearning(id={self.id}, prd_id={self.prd_id})>"
