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

"""Append-only trail of changes to an org's celebration settings.

Switching celebrations on starts publishing personal dates about everyone
who has not opted out, and the channel decides who reads them. HR and
admins share this page, with admins alone owning the channel, so every
change is recorded with who made it. Only field names and their old/new
values are kept.

Nothing updates or deletes these rows: the repository only appends.
Mirrors :class:`app.models.leave_config_event.LeaveConfigEvent`.
"""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class CelebrationConfigAction(StrEnum):
    """What kind of change was made."""

    ENABLED = "enabled"
    DISABLED = "disabled"
    # The channel or the @channel ping — admin/owner-only fields.
    CHANNEL_CHANGED = "channel_changed"
    # Any other field (time, days, streams, GIFs) with no on/off or channel change.
    UPDATED = "updated"


class CelebrationConfigEvent(BaseModel):
    """One change to an org's celebration settings."""

    __tablename__ = "celebration_config_events"
    __table_args__ = (Index("ix_celebration_config_events_org", "org_id", "created_at"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[CelebrationConfigAction] = mapped_column(
        Enum(
            CelebrationConfigAction,
            name="celebration_config_action",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    # {"field": [old, new]} for every field that changed.
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    def __repr__(self) -> str:
        return f"<CelebrationConfigEvent(org_id={self.org_id}, action={self.action})>"
