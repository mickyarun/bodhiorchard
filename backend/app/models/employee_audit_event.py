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

"""Who looked at or changed an employee's sensitive details or documents.

Append-only: a database trigger refuses UPDATE and DELETE, so even code
with database access can't quietly erase a reveal. Carries ids and field
names only, never the values.
"""

import uuid
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class EmployeeAuditAction(StrEnum):
    """What happened."""

    FIELD_REVEALED = "field_revealed"
    DETAILS_UPDATED = "details_updated"
    DOCUMENT_UPLOADED = "document_uploaded"
    DOCUMENT_VIEWED = "document_viewed"
    DOCUMENT_DELETED = "document_deleted"


class EmployeeAuditEvent(BaseModel):
    """One access or change."""

    __tablename__ = "employee_audit_events"
    __table_args__ = (
        Index("ix_employee_audit_events_profile", "org_id", "profile_id", "created_at"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    # No cascades: the trail outlives the people and documents in it.
    actor_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    subject_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The record the entry is about. Stable across account merges (which
    # move the profile to the surviving user), so the log follows the record.
    profile_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    action: Mapped[EmployeeAuditAction] = mapped_column(
        Enum(
            EmployeeAuditAction,
            name="employee_audit_action",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    # A field name ("bank_account_number") or a document id.
    target: Mapped[str] = mapped_column(String(100), nullable=False)
