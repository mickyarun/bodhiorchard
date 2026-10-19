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

"""Append-only leave balance ledger.

A balance is never stored: it's the year's allocation plus adjustments,
minus approved and pending request days. A type's allocation row is
written once, on the member's first submit or approval spending it that
year, which freezes it — a later quota or proration change can't rewrite
a year already in use. Until then it's worked out live.
"""

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Enum, ForeignKey, Index, Numeric, SmallInteger, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class LedgerEntryType(StrEnum):
    """Allocation (one per user, type and year), a manual adjustment, or a
    correction made by recalculating a frozen allocation."""

    ALLOCATION = "allocation"
    ADJUSTMENT = "adjustment"
    # Written by "recalculate allocation": the gap between the frozen
    # allocation (plus earlier corrections) and what it should be now.
    CORRECTION = "correction"


class LeaveLedgerEntry(BaseModel):
    """One credit or debit to a member's balance of one leave type."""

    __tablename__ = "leave_ledger"
    __table_args__ = (
        Index(
            "uq_leave_ledger_allocation",
            "user_id",
            "leave_type_id",
            "leave_year",
            unique=True,
            postgresql_where="entry_type = 'allocation'",
        ),
        Index("ix_leave_ledger_lookup", "org_id", "user_id", "leave_year"),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    leave_type_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leave_types.id", ondelete="RESTRICT"), nullable=False
    )
    # Calendar year in which the leave year starts (Apr 2026–Mar 2027 → 2026).
    leave_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    entry_type: Mapped[LedgerEntryType] = mapped_column(
        Enum(
            LedgerEntryType,
            name="leave_ledger_entry_type",
            values_callable=lambda e: [x.value for x in e],
        ),
        nullable=False,
    )
    days: Mapped[Decimal] = mapped_column(Numeric(5, 1), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    def __repr__(self) -> str:
        return f"<LeaveLedgerEntry(type={self.entry_type}, days={self.days})>"
