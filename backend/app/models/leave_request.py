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

"""A leave, work-from-home or optional-holiday request.

There is no stored approver: approvers are the requester's current active
reporting managers (else HR), so reassigning a manager moves pending
requests with them.
"""

import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Index, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


def _values(enum_cls: type[StrEnum]) -> list[str]:
    return [member.value for member in enum_cls]


class LeaveKind(StrEnum):
    """What is being requested."""

    LEAVE = "leave"
    WFH = "wfh"
    OPTIONAL_HOLIDAY = "optional_holiday"


class HalfDay(StrEnum):
    """Part of a single day; only for one-day requests."""

    NONE = "none"
    FIRST_HALF = "first_half"
    SECOND_HALF = "second_half"


class LeaveStatus(StrEnum):
    """Lifecycle of a request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class ApprovalMode(StrEnum):
    """Who approved: a person, or the policy (auto-approved WFH)."""

    MANUAL = "manual"
    AUTO_POLICY = "auto_policy"


class LeaveRequest(BaseModel):
    """One request by one member."""

    __tablename__ = "leave_requests"
    __table_args__ = (
        Index("ix_leave_requests_org_dates", "org_id", "start_date", "end_date"),
        Index("ix_leave_requests_user_start", "org_id", "user_id", "start_date"),
        Index(
            "ix_leave_requests_pending",
            "org_id",
            "user_id",
            postgresql_where="status = 'pending'",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    # The policy in force when the request was made; balances stay on it.
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leave_policies.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[LeaveKind] = mapped_column(
        Enum(LeaveKind, name="leave_kind", values_callable=_values), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=True
    )
    holiday_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("policy_holidays.id", ondelete="SET NULL"), nullable=True
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    half_day: Mapped[HalfDay] = mapped_column(
        Enum(HalfDay, name="leave_half_day", values_callable=_values),
        nullable=False,
        default=HalfDay.NONE,
    )
    days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[LeaveStatus] = mapped_column(
        Enum(LeaveStatus, name="leave_status", values_callable=_values),
        nullable=False,
        default=LeaveStatus.PENDING,
    )
    approval_mode: Mapped[ApprovalMode] = mapped_column(
        Enum(ApprovalMode, name="leave_approval_mode", values_callable=_values),
        nullable=False,
        default=ApprovalMode.MANUAL,
    )
    decided_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    def __repr__(self) -> str:
        return f"<LeaveRequest(id={self.id}, kind={self.kind}, status={self.status})>"
