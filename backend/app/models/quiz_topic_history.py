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

"""Per-org ledger of quiz topics already used, to prevent repetition.

A topic is recorded here when a question is approved (and on use), so a rejected
draft never permanently burns a topic. Batch generation reads recent
``topic_label`` rows (plus the topics of pending pool questions) as a denylist
fed to the agent, and ``quiz_persist`` hard-drops any draft whose ``topic_hash``
already exists here — belt-and-suspenders against the model ignoring the denylist.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class QuizTopicHistory(BaseModel):
    """A topic that has been used for an org's quiz, keyed by a stable hash."""

    __tablename__ = "quiz_topic_history"
    __table_args__ = (UniqueConstraint("org_id", "topic_hash", name="uq_quiz_topic_org_hash"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    topic_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    topic_label: Mapped[str] = mapped_column(String(255), nullable=False)
    last_used_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    def __repr__(self) -> str:
        return f"<QuizTopicHistory(org={self.org_id}, label={self.topic_label!r})>"
