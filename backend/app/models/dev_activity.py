"""Developer activity log model for tracking real-time progress via MCP."""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class DevActivityLog(BaseModel):
    """Developer activity updates reported via MCP or post-commit hooks.

    Each row represents a single status update from a developer's Claude Code
    session. The metadata_ JSONB column stores optional stats, file lists,
    and AI self-assessment (effectiveness) data.
    """

    __tablename__ = "dev_activity_logs"
    __table_args__ = (
        Index("ix_dev_activity_bud_id", "bud_id"),
        Index("ix_dev_activity_org_created", "org_id", "created_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False,
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bud_documents.id", ondelete="CASCADE"), nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return f"<DevActivityLog(bud_id={self.bud_id}, status={self.status!r})>"
