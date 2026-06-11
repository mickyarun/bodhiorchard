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

"""Feature Q&A session model for Slack-based feature lookups."""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class FeatureQAStatus(StrEnum):
    """State machine for a Slack feature Q&A conversation."""

    AWAITING_USER = "awaiting_user"
    RESOLVED = "resolved"
    ERRORED = "errored"


class FeatureQASession(BaseModel):
    """Tracks a Slack-based feature Q&A conversation.

    Created when a user @-mentions the bot or reacts ❓ to a message.
    Persists multi-turn state so follow-up clarifications in the same
    thread are routed back to the same agent loop.
    """

    __tablename__ = "feature_qa_sessions"
    __table_args__ = (
        UniqueConstraint("org_id", "channel", "thread_ts", name="uq_fqa_org_thread"),
        Index("ix_fqa_org_status", "org_id", "status"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    channel: Mapped[str] = mapped_column(String(50), nullable=False)
    thread_ts: Mapped[str] = mapped_column(String(50), nullable=False)
    requester_slack_user_id: Mapped[str] = mapped_column(String(50), nullable=False)
    original_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[FeatureQAStatus] = mapped_column(
        Enum(
            FeatureQAStatus,
            name="feature_qa_status",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
        default=FeatureQAStatus.AWAITING_USER,
    )
    # JSONB context: stores candidate matches and last agent turn for multi-turn clarification
    context: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    # CLI model the thread's Claude session was minted with, persisted on
    # the first (claiming) turn. A resumed turn reuses this exact model so
    # the conversation never switches models mid-thread — correct even once
    # per-org Agent-Prompt overrides can change a specialist's model. NULL
    # on legacy / triage-seeded rows; resume falls back to the module default.
    cli_model: Mapped[str | None] = mapped_column(String(50), nullable=True)

    def __repr__(self) -> str:
        return (
            f"<FeatureQASession(id={self.id}, channel={self.channel!r}, status={self.status!r})>"
        )
