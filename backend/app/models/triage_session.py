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

"""Triage session model for Slack-based feature intake conversations."""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class TriageStatus(StrEnum):
    """State machine for a triage conversation."""

    INTERVIEWING = "interviewing"
    CHECKING = "checking"
    AWAITING_PM = "awaiting_pm"
    APPROVED = "approved"
    REJECTED = "rejected"
    BUD_CREATED = "bud_created"


class TriageSession(BaseModel):
    """Tracks a Slack-based feature intake triage conversation.

    Each session is anchored to a Slack thread (channel + thread_ts)
    and progresses through the TriageStatus state machine.
    """

    __tablename__ = "triage_sessions"
    __table_args__ = (
        UniqueConstraint("org_id", "slack_channel", "thread_ts", name="uq_triage_org_thread"),
        Index("ix_triage_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    slack_channel: Mapped[str] = mapped_column(String(50), nullable=False)
    thread_ts: Mapped[str] = mapped_column(String(50), nullable=False)
    original_msg_ts: Mapped[str] = mapped_column(String(50), nullable=False)
    summary_msg_ts: Mapped[str | None] = mapped_column(String(50), nullable=True)
    requester_slack_id: Mapped[str] = mapped_column(String(50), nullable=False)
    requester_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    original_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    # "bud" (default, existing flow) or "bug" (bug triage via 🐛)
    session_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="bud", server_default="bud"
    )
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default=TriageStatus.INTERVIEWING
    )
    priority: Mapped[str | None] = mapped_column(String(20), nullable=True)
    feature_name: Mapped[str | None] = mapped_column(String(500), nullable=True)
    triage_context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    bud_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("bud_documents.id"), nullable=True
    )

    def __repr__(self) -> str:
        return (
            f"<TriageSession(id={self.id}, channel={self.slack_channel!r}, "
            f"status={self.status!r})>"
        )
