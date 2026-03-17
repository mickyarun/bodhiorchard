"""Agent execution log model for observability."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AgentLog(BaseModel):
    """Records each AI agent invocation for auditing and debugging."""

    __tablename__ = "agent_logs"

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    agent_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trigger_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    trigger_source: Mapped[str | None] = mapped_column(String(255), nullable=True)
    input_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    output_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    execution_time_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<AgentLog(id={self.id}, agent_name={self.agent_name!r})>"
