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

"""Leave policy: the rules for one country or location.

Each policy carries its own leave types and quotas, holiday calendar,
working days, timezone, WFH approval rule, leave year and the rule for
prorating new joiners' allocations. Every employee
follows exactly one policy: the one on their profile, else the org's
default.
"""

import uuid
from enum import StrEnum

from sqlalchemy import (
    Boolean,
    Enum,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class WfhApproval(StrEnum):
    """How work-from-home requests are approved under a policy."""

    REQUIRED = "required"
    AUTO = "auto"
    # The first N WFH days in a calendar month need no approval.
    AUTO_WITHIN_ALLOWANCE = "auto_within_allowance"


class ProrationMethod(StrEnum):
    """How a part-year allocation is worked out for someone who joins (or
    moves onto the policy) after the leave year starts."""

    # Full quota whatever the joining date.
    NONE = "none"
    # Share of the year's calendar days left from the joining date.
    DAILY = "daily"
    # Share of whole months left; the joining month counts only when they
    # join on or before ``proration_cutoff_day``.
    MONTHLY = "monthly"


class AllocationRounding(StrEnum):
    """How a prorated allocation is rounded: step and direction."""

    NONE = "none"  # kept to one decimal place, the ledger's precision
    NEAREST_HALF = "nearest_half"
    UP_HALF = "up_half"
    DOWN_HALF = "down_half"
    NEAREST_WHOLE = "nearest_whole"
    UP_WHOLE = "up_whole"
    DOWN_WHOLE = "down_whole"


def _enum_values(enum: type[StrEnum]) -> list[str]:
    return [member.value for member in enum]


class LeavePolicy(BaseModel):
    """Per-country (or per-location) leave rules."""

    __tablename__ = "leave_policies"
    __table_args__ = (
        UniqueConstraint("org_id", "name", name="uq_leave_policies_org_name"),
        Index(
            "uq_leave_policies_org_default",
            "org_id",
            unique=True,
            postgresql_where="is_default",
        ),
    )

    org_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("organizations.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    # ISO 3166-1 alpha-2 and python-holidays subdivision code (e.g. "TN").
    country_code: Mapped[str | None] = mapped_column(String(2), nullable=True)
    subdivision_code: Mapped[str | None] = mapped_column(String(10), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    # 0 = Monday … 6 = Sunday.
    working_days: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), nullable=False, default=lambda: [0, 1, 2, 3, 4]
    )
    year_start_month: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=1)
    wfh_approval: Mapped[WfhApproval] = mapped_column(
        Enum(WfhApproval, name="wfh_approval", values_callable=lambda e: [x.value for x in e]),
        nullable=False,
        default=WfhApproval.REQUIRED,
    )
    wfh_monthly_auto_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    backdate_limit_days: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=7)
    optional_holiday_quota: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    proration_method: Mapped[ProrationMethod] = mapped_column(
        Enum(ProrationMethod, name="leave_proration_method", values_callable=_enum_values),
        nullable=False,
        default=ProrationMethod.DAILY,
        server_default=ProrationMethod.DAILY.value,
    )
    # Monthly proration: joining on or before this day counts the month.
    proration_cutoff_day: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, default=15, server_default="15"
    )
    allocation_rounding: Mapped[AllocationRounding] = mapped_column(
        Enum(AllocationRounding, name="leave_allocation_rounding", values_callable=_enum_values),
        nullable=False,
        default=AllocationRounding.NEAREST_HALF,
        server_default=AllocationRounding.NEAREST_HALF.value,
    )
    is_default: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )

    def __repr__(self) -> str:
        return f"<LeavePolicy(id={self.id}, name={self.name!r})>"
