# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""BUD agent task model for persistent agent execution tracking.

Tracks each AI agent execution against a BUD — status, progress,
errors, and retry history. Replaces the fragile metadata-based
job ID tracking pattern.
"""

import uuid
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.agent_skill import AgentSkill
    from app.models.bud import BUDDocument


class AgentTaskStatus(StrEnum):
    """Lifecycle states for an agent task."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class BUDAgentTask(BaseModel):
    """Persistent record of an AI agent job execution against a BUD.

    Each row tracks one attempt at running an agent skill on a BUD.
    Failed tasks can be retried (creating a new row with incremented
    ``attempt``). The partial unique index ensures at most one
    pending/running task per BUD at any time.
    """

    __tablename__ = "bud_agent_tasks"
    __table_args__ = (
        Index("ix_bud_agent_tasks_bud_status", "bud_id", "status"),
        Index("ix_bud_agent_tasks_org_status", "org_id", "status"),
        Index("ix_bud_agent_tasks_job_id", "job_id"),
        Index(
            "uq_bud_agent_tasks_one_active",
            "bud_id",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    skill_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("agent_skills.id", ondelete="RESTRICT"),
        nullable=False,
    )
    task_type: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=AgentTaskStatus.PENDING, server_default="pending"
    )
    job_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    status_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    triggered_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    skill: Mapped["AgentSkill"] = relationship(lazy="joined")
    bud: Mapped["BUDDocument"] = relationship(back_populates="agent_tasks")

    def __repr__(self) -> str:
        return (
            f"<BUDAgentTask(id={self.id}, type={self.task_type!r}, "
            f"status={self.status!r}, attempt={self.attempt})>"
        )
