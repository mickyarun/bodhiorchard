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

"""A member's permission for Bodhiorchard to set their Slack status.

Slack only lets a bot set its own status, so each person approves once
and we keep their user token (encrypted) to show "Working from home" or
"On leave" on the days they are. A Slack account (its user id) is driven
by one org at a time: connecting it in another org hands it over.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class SlackStatusLink(BaseModel):
    """One member's Slack user token, for their status only."""

    __tablename__ = "slack_status_links"
    __table_args__ = (
        UniqueConstraint("org_id", "user_id", name="uq_slack_status_links_org_user"),
        Index("ix_slack_status_links_slack_user", "slack_user_id"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # Workspace (or enterprise) the token was granted in; for reference only.
    slack_team_id: Mapped[str] = mapped_column(String(32), nullable=False)
    slack_user_id: Mapped[str] = mapped_column(String(32), nullable=False)
    # Encrypted with the app's key (users.profile:read/write only).
    token: Mapped[str] = mapped_column(Text, nullable=False)
    # When their status is next due: their next local midnight once set for
    # the day; None = now (just connected). Lets an idle tick be one query.
    next_refresh_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
