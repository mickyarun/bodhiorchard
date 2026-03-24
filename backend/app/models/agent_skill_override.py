"""Agent skill override model for storing per-org customized agent prompts."""

import uuid

from sqlalchemy import ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AgentSkillOverride(BaseModel):
    """Per-org override of an agent skill prompt.

    File-based skills in agents/skills/ serve as defaults.
    When an override row exists for a given org + skill_slug,
    the DB version takes precedence.
    """

    __tablename__ = "agent_skill_overrides"
    __table_args__ = (UniqueConstraint("org_id", "skill_slug", name="uq_skill_override_org_slug"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    skill_slug: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    mcp_tools: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    max_turns: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    model: Mapped[str] = mapped_column(String(100), nullable=False, default="", server_default="")
    effort: Mapped[str] = mapped_column(String(20), nullable=False, default="", server_default="")

    def __repr__(self) -> str:
        return f"<AgentSkillOverride(id={self.id}, org={self.org_id}, slug={self.skill_slug!r})>"
