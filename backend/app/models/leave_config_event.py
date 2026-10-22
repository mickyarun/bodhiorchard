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

"""Append-only trail of changes to leave configuration.

Who changed a quota, a policy's rules, the default policy, a library leave
type, or moved people between policies — so a change that benefits the person making it
can always be traced. Only field names and their old/new values are
kept; there are no free-text reasons here. Balance adjustments are
already traced by their ledger rows (``created_by`` plus a note).

Nothing updates or deletes these rows: the repository only appends.
"""

import uuid
from enum import StrEnum
from typing import Any

from sqlalchemy import Enum, ForeignKey, Index
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class LeaveConfigAction(StrEnum):
    """What kind of change was made."""

    POLICY_CREATED = "policy_created"
    POLICY_UPDATED = "policy_updated"
    POLICY_MADE_DEFAULT = "policy_made_default"
    POLICY_DELETED = "policy_deleted"
    TYPE_CREATED = "type_created"
    TYPE_UPDATED = "type_updated"
    EMPLOYEES_ASSIGNED = "employees_assigned"
    # The org's leave type library: these have no policy (policy_id is NULL).
    LIBRARY_TYPE_CREATED = "library_type_created"
    LIBRARY_TYPE_UPDATED = "library_type_updated"
    LIBRARY_TYPE_DELETED = "library_type_deleted"


class LeaveConfigEvent(BaseModel):
    """One change to a policy or its leave types."""

    __tablename__ = "leave_config_events"
    __table_args__ = (Index("ix_leave_config_events_policy", "org_id", "policy_id", "created_at"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    actor_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # Kept when the policy is deleted, so its deletion stays on record.
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("leave_policies.id", ondelete="SET NULL", name="fk_leave_config_events_policy"),
        nullable=True,
    )
    action: Mapped[LeaveConfigAction] = mapped_column(
        Enum(
            LeaveConfigAction,
            name="leave_config_action",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    # {"field": [old, new]}, or {"user_ids": [...]} for assignments.
    changes: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
