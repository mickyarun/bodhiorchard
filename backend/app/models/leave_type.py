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

"""A kind of leave (Casual, Sick, Unpaid …) within one leave policy."""

import uuid
from decimal import Decimal
from enum import StrEnum

from sqlalchemy import Boolean, Enum, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel
from app.models.employee_profile import Gender


class LeaveAccrual(StrEnum):
    """When a year's allowance becomes available to use."""

    # All of it on the first day of the leave year (or of joining).
    UPFRONT = "upfront"
    # An equal part on the 1st of each month: 18 a year is 1.5 a month.
    MONTHLY = "monthly"


def _values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


class LeaveType(BaseModel):
    """Leave type with its yearly quota; deactivated rather than deleted."""

    __tablename__ = "leave_types"
    __table_args__ = (UniqueConstraint("policy_id", "code", name="uq_leave_types_policy_code"),)

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    policy_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("leave_policies.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    # NULL = no limit (e.g. unpaid leave).
    annual_quota_days: Mapped[Decimal | None] = mapped_column(Numeric(5, 1), nullable=True)
    is_paid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Counts toward the policy's high-leave heads-up and warning.
    counts_toward_warning: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )
    # Unused days are paid out when someone leaves (their full and final).
    is_encashable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    accrual: Mapped[LeaveAccrual] = mapped_column(
        Enum(LeaveAccrual, name="leave_accrual", values_callable=_values),
        nullable=False,
        default=LeaveAccrual.UPFRONT,
        server_default=LeaveAccrual.UPFRONT.value,
    )
    # Only people whose profile gender is one of these can see and request
    # it (period leave: female). NULL = everyone on the policy.
    eligible_genders: Mapped[list[Gender] | None] = mapped_column(
        ARRAY(Enum(Gender, name="employee_gender", values_callable=_values, create_type=False)),
        nullable=True,
    )
    # Approved as soon as it's sent; the managers get a heads-up instead.
    auto_approve: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # At most this many days in any calendar month; unused days don't carry
    # over. NULL = no monthly limit.
    monthly_limit_days: Mapped[Decimal | None] = mapped_column(Numeric(3, 1), nullable=True)
    # Requests past the balance are refused (people use another type) instead
    # of the extra days becoming loss of pay. Sick leave, usually.
    stops_at_balance: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    # A palette slot ("swatch-1" … "swatch-7"); only HR and the requester see it.
    color_key: Mapped[str] = mapped_column(String(20), nullable=False, default="swatch-1")
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )

    def __repr__(self) -> str:
        return f"<LeaveType(id={self.id}, code={self.code!r})>"
