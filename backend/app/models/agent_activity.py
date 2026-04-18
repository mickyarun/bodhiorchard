"""Agent activity log model for tracking all agent skill execution events.

Stores activity from two sources:
- Backend (source='backend'): skill_invoked, skill_completed, skill_failed
- Claude Code hooks (source='claude_hook'): session lifecycle, commits, file changes

Linked to agent_skills via skill_id (resolved from skill_slug) and
optionally to bud_agent_tasks via task_id.
"""

import uuid

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AgentActivityLog(BaseModel):
    """Agent activity log for skill execution events.

    Tracks both high-level lifecycle events logged by the backend
    and fine-grained events from Claude Code hooks in tracked repos.
    Clean separation from dev_activity_logs: agent sessions route here
    via BODHIORCHARD_AGENT_SKILL_SLUG env var detection in hooks.
    """

    __tablename__ = "agent_activity_logs"
    __table_args__ = (
        Index("ix_agent_activity_org_created", "org_id", "created_at"),
        Index("ix_agent_activity_session_id", "session_id"),
        Index("ix_agent_activity_skill_id", "skill_id"),
        Index("ix_agent_activity_bud_id", "bud_id"),
        Index("ix_agent_activity_event_type", "event_type"),
        Index("ix_agent_activity_task_id", "task_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_skills.id"),
        nullable=True,
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_agent_tasks.id"),
        nullable=True,
    )
    bud_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=True,
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    repo_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tracked_repositories.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str | None] = mapped_column(String(50), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    skill_slug: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    agent_type: Mapped[str | None] = mapped_column(
        String(100),
        nullable=True,
    )
    actor_name: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
    )
    branch: Mapped[str | None] = mapped_column(String(500), nullable=True)
    commit_sha: Mapped[str | None] = mapped_column(
        String(40),
        nullable=True,
    )
    file_path: Mapped[str | None] = mapped_column(
        String(1000),
        nullable=True,
    )
    files_changed: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<AgentActivityLog(event_type={self.event_type!r}, "
            f"skill_slug={self.skill_slug!r}, session_id={self.session_id!r})>"
        )
