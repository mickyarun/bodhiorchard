"""Developer skill profile model for intelligent task assignment."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SkillProfile(BaseModel):
    """Tracks developer expertise per module for intelligent routing."""

    __tablename__ = "skill_profiles"
    __table_args__ = (
        UniqueConstraint("user_id", "org_id", "module", name="uq_skill_user_org_module"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    module: Mapped[str] = mapped_column(String(255), nullable=False)
    repo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    languages: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    skill_score: Mapped[float] = mapped_column(
        Numeric(precision=3, scale=2), nullable=False, default=0.0
    )
    touch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_touch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<SkillProfile(user_id={self.user_id}, module={self.module!r})>"
