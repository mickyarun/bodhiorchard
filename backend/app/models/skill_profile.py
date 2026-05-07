# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Developer skill profile model for intelligent task assignment."""

import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
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
        Index("ix_sp_org_score", "org_id", "skill_score"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    module: Mapped[str] = mapped_column(String(255), nullable=False)
    feature_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("features.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    languages: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    skill_score: Mapped[float] = mapped_column(
        Numeric(precision=3, scale=2), nullable=False, default=0.0
    )
    touch_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_touch: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    def __repr__(self) -> str:
        return f"<SkillProfile(user_id={self.user_id}, module={self.module!r})>"
