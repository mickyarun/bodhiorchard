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

"""Holidays on a leave policy's calendar — mandatory or optional."""

import uuid
from datetime import date
from enum import StrEnum

from sqlalchemy import Date, Enum, ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class HolidayKind(StrEnum):
    """Everyone is off on a mandatory holiday; optional ones are picked."""

    MANDATORY = "mandatory"
    OPTIONAL = "optional"


class HolidaySource(StrEnum):
    """Where the holiday row came from."""

    MANUAL = "manual"
    IMPORTED = "imported"


class PolicyHoliday(BaseModel):
    """One holiday on one policy's calendar."""

    __tablename__ = "policy_holidays"
    __table_args__ = (UniqueConstraint("policy_id", "date", name="uq_policy_holidays_date"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leave_policies.id", ondelete="CASCADE"), nullable=False
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    kind: Mapped[HolidayKind] = mapped_column(
        Enum(HolidayKind, name="holiday_kind", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=HolidayKind.MANDATORY,
    )
    source: Mapped[HolidaySource] = mapped_column(
        Enum(HolidaySource, name="holiday_source", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=HolidaySource.MANUAL,
    )

    def __repr__(self) -> str:
        return f"<PolicyHoliday(date={self.date}, name={self.name!r})>"
