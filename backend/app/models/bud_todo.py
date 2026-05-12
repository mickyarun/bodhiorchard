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

"""BUD implementation TODO model.

Tracks discrete work items parsed from the tech spec's Implementation
TODO section.  Each TODO can be independently assigned, claimed via
MCP, and completed — enabling multi-developer work within a single
BUD phase.
"""

import uuid
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import BaseModel

if TYPE_CHECKING:
    from app.models.bud import BUDDocument
    from app.models.user import User


class BUDTodoStatus(StrEnum):
    """Lifecycle states for a TODO item."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


class BUDTodo(BaseModel):
    """A discrete work item parsed from a BUD's tech spec.

    Created automatically when the tech-arch agent completes.
    Developers claim individual TODOs via the UI or MCP
    ``takeover_todo`` tool, enabling parallel work on the same BUD.
    """

    __tablename__ = "bud_todos"
    __table_args__ = (
        UniqueConstraint("bud_id", "sequence", name="uq_bud_todo_seq"),
        Index("ix_bud_todo_bud", "bud_id"),
        Index("ix_bud_todo_assignee", "assignee_id"),
        Index("ix_bud_todo_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("organizations.id"),
        nullable=False,
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    phase: Mapped[str] = mapped_column(String(30), nullable=False, default="development")
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default=BUDTodoStatus.PENDING,
        server_default="pending",
    )
    is_checkpoint: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    context_md: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    repo_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    code_locations: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb")
    )
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detail: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Relationships
    bud: Mapped["BUDDocument"] = relationship(back_populates="todos", lazy="selectin")
    assignee: Mapped["User | None"] = relationship(lazy="joined")

    def __repr__(self) -> str:
        return (
            f"<BUDTodo(id={self.id}, seq={self.sequence}, "
            f"status={self.status!r}, title={self.title[:40]!r})>"
        )
