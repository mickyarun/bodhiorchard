# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Design system reference model for storing extracted frontend tokens per-org."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DesignSystemRef(BaseModel):
    """Extracted design system tokens stored per-org, linked to a tracked repository."""

    __tablename__ = "design_system_refs"
    __table_args__ = (UniqueConstraint("org_id", "repo_id", name="uq_design_system_org_repo"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    repo_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tracked_repositories.id"), nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    def __repr__(self) -> str:
        return f"<DesignSystemRef(id={self.id}, org_id={self.org_id}, default={self.is_default})>"
