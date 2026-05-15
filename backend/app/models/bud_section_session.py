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

"""Originating-agent Claude CLI session tracking per BUD section.

Each BUD section (``requirements_md``, ``tech_spec_md``, ``test_plan_md``,
``design``, ``testing``) is authored by an AI agent that owns a Claude CLI
session id. Subsequent chat turns on that section pass ``--resume`` against
the *same* session id so the agent's prior reasoning, tool calls, and prompt
cache are preserved.

One row per ``(bud_id, section[, design_id])``. ``design`` is keyed by
design row id so per-repo wireframes have independent threads; other
sections share one thread per BUD. When the message count hits the cap
defined in :mod:`app.schemas.bud_constants`, the repository rotates the row to a
new session id (a fresh CLI namespace).
"""

import uuid
from datetime import datetime
from enum import StrEnum

from sqlalchemy import DateTime, Enum, ForeignKey, Index, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class ChatActiveJobStatus(StrEnum):
    """Lifecycle state of the in-flight chat job on a section session row.

    Only non-terminal states appear here — the worker clears the pointer
    on COMPLETED / FAILED / CANCELLED so the DB column is always either
    ``None`` (no job in flight) or one of these two values.
    """

    QUEUED = "queued"
    RUNNING = "running"


class BUDSectionSession(BaseModel):
    """Active Claude CLI session id for a BUD section (one row per thread)."""

    __tablename__ = "bud_section_sessions"
    # Two partial unique indexes cover the same intent as a single
    # ``UNIQUE NULLS NOT DISTINCT`` constraint without requiring PG 15+.
    # SQL's NULL != NULL means a plain UNIQUE over (bud_id, section,
    # design_id) lets duplicate non-design rows slip through because
    # they all carry design_id=NULL. Splitting on NULL vs NOT NULL
    # enforces "one current thread per (bud, section)" for ordinary
    # sections and "one per (bud, section, design)" for design rows.
    __table_args__ = (
        Index(
            "uq_bud_section_sessions_bud_section",
            "bud_id",
            "section",
            unique=True,
            postgresql_where="design_id IS NULL",
        ),
        Index(
            "uq_bud_section_sessions_bud_section_design",
            "bud_id",
            "section",
            "design_id",
            unique=True,
            postgresql_where="design_id IS NOT NULL",
        ),
        # Speeds up the boot-time orphan sweep ("which sessions still
        # claim an in-flight chat job that no longer exists?") without
        # paying full-table-scan cost on every startup.
        Index(
            "ix_bud_section_sessions_active_job",
            "bud_id",
            "section",
            "design_id",
            postgresql_where="active_job_id IS NOT NULL",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    bud_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    section: Mapped[str] = mapped_column(String(30), nullable=False)
    design_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("bud_designs.id", ondelete="CASCADE"),
        nullable=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    message_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── In-flight chat job pointer ──────────────────────────────────
    # Set atomically when ``POST /chat`` enqueues a job (acts as the
    # concurrency lock for the section) and cleared by the worker in
    # the terminal-path finally block. A row whose pointer is non-NULL
    # after a backend restart is an orphan and gets swept on startup.
    active_job_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    active_job_status: Mapped[ChatActiveJobStatus | None] = mapped_column(
        # ``values_callable`` makes SQLAlchemy send the StrEnum *values*
        # (``"queued"``, ``"running"``) instead of the member names
        # (``"QUEUED"``, ``"RUNNING"``), matching JobState and the rest
        # of the codebase's enum convention.
        Enum(
            ChatActiveJobStatus,
            name="chat_active_job_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    active_job_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<BUDSectionSession(bud_id={self.bud_id}, section={self.section}, "
            f"session_id={self.session_id}, message_count={self.message_count})>"
        )
