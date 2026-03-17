"""Standup report model for daily team status tracking."""

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class StandupReport(BaseModel):
    """AI-generated daily standup report for an organization."""

    __tablename__ = "standup_reports"
    __table_args__ = (UniqueConstraint("org_id", "date", name="uq_standup_org_date"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    content: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    posted_to_slack_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return f"<StandupReport(org_id={self.org_id}, date={self.date})>"
