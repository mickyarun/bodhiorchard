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

"""DTOs for configuring leave policies, types, holidays and balances."""

import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.employee_profile import Gender
from app.models.leave_policy import AllocationRounding, ProrationMethod, WfhApproval
from app.models.leave_type import LeaveAccrual
from app.models.policy_holiday import HolidayKind, HolidaySource
from app.schemas.leave import PersonRef
from app.schemas.leave_summary import Balance, LeaveYear
from app.schemas.settings import validate_optional_timezone


class PolicyWrite(BaseModel):
    """Create or update a leave policy."""

    name: str = Field(..., min_length=1, max_length=100)
    country_code: str | None = Field(None, min_length=2, max_length=2)
    subdivision_code: str | None = Field(None, max_length=10)
    timezone: str = Field("UTC", max_length=64)
    working_days: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4], min_length=1)
    year_start_month: int = Field(1, ge=1, le=12)
    wfh_approval: WfhApproval = WfhApproval.REQUIRED
    wfh_monthly_auto_days: int = Field(0, ge=0, le=31)
    backdate_limit_days: int = Field(7, ge=0, le=365)
    optional_holiday_quota: int = Field(0, ge=0, le=60)
    # Heads-up, then warning, after this many days of leave in a year.
    leave_notice_days: int | None = Field(None, ge=1, le=365)
    leave_warning_days: int | None = Field(None, ge=1, le=365)
    proration_method: ProrationMethod = ProrationMethod.DAILY
    proration_cutoff_day: int = Field(15, ge=1, le=31)
    allocation_rounding: AllocationRounding = AllocationRounding.NEAREST_HALF

    @field_validator("working_days")
    @classmethod
    def _weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 0 or day > 6 for day in value):
            raise ValueError("Working days are 0 (Monday) to 6 (Sunday).")
        return sorted(set(value))

    @field_validator("country_code")
    @classmethod
    def _upper(cls, value: str | None) -> str | None:
        return value.upper() if value else None

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str) -> str:
        checked = validate_optional_timezone(value)
        if checked is None:
            raise ValueError("Choose a timezone, e.g. Asia/Kolkata.")
        return checked

    @model_validator(mode="after")
    def _warning_after_notice(self) -> "PolicyWrite":
        notice, warning = self.leave_notice_days, self.leave_warning_days
        if notice is not None and warning is not None and warning < notice:
            raise ValueError("The warning should come at or after the heads-up.")
        return self


class PolicyRead(PolicyWrite):
    """A policy with its id and how many employees follow it."""

    id: uuid.UUID
    is_default: bool
    employee_count: int
    has_requests: bool


class LeaveTypeWrite(BaseModel):
    """Create or update a leave type."""

    name: str = Field(..., min_length=1, max_length=100)
    code: str = Field(..., min_length=1, max_length=10)
    annual_quota_days: Decimal | None = Field(None, ge=0, le=365, decimal_places=1)
    # Upfront: the whole allowance on day one. Monthly: an equal part each month.
    accrual: LeaveAccrual = LeaveAccrual.UPFRONT
    is_paid: bool = True
    is_encashable: bool = False
    counts_toward_warning: bool = True
    # Only these profile genders can see and request it; None = everyone.
    eligible_genders: list[Gender] | None = None
    auto_approve: bool = False
    # At most this many days in a calendar month, with no carry-over; None = no limit.
    monthly_limit_days: Decimal | None = Field(None, ge=0.5, le=31, decimal_places=1)
    color_key: str = Field("swatch-1", pattern=r"^swatch-[1-7]$")
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        return value.strip().upper()

    @field_validator("eligible_genders")
    @classmethod
    def _genders(cls, value: list[Gender] | None) -> list[Gender] | None:
        if value is None:
            return None
        if not value:
            raise ValueError("Pick at least one gender, or let everyone use it.")
        return sorted(set(value))

    @field_validator("monthly_limit_days")
    @classmethod
    def _half_days(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value * 2) % 1:
            raise ValueError("Use whole or half days, e.g. 1 or 1.5.")
        return value

    @model_validator(mode="after")
    def _auto_needs_allowance(self) -> "LeaveTypeWrite":
        # Unlimited leave that approves itself would need nobody's say at all.
        if self.auto_approve and self.annual_quota_days is None:
            raise ValueError("A type that approves itself needs a yearly allowance.")
        return self


class LeaveTypeRead(LeaveTypeWrite):
    """A leave type with its id."""

    id: uuid.UUID
    policy_id: uuid.UUID


class HolidayWrite(BaseModel):
    """Add or edit a holiday."""

    date: date
    name: str = Field(..., min_length=1, max_length=150)
    kind: HolidayKind = HolidayKind.MANDATORY


class HolidayAdminRead(HolidayWrite):
    """A holiday with where it came from."""

    id: uuid.UUID
    source: HolidaySource


class HolidayImport(BaseModel):
    """Import a year's public holidays for the policy's country."""

    year: int = Field(..., ge=2000, le=2100)


class HolidayImportResult(BaseModel):
    """How many holidays were added; existing dates are left alone."""

    added: int
    skipped: int


class Subdivision(BaseModel):
    """A state or region with its own public holidays."""

    code: str
    name: str


class HolidayCountry(BaseModel):
    """A country python-holidays can import."""

    code: str
    name: str
    subdivisions: list[Subdivision]


class PolicyAssign(BaseModel):
    """Move employees onto a policy."""

    user_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=500)


class LedgerEntryRead(BaseModel):
    """One allocation or adjustment."""

    id: uuid.UUID
    leave_type_id: uuid.UUID
    leave_year: int
    entry_type: str
    days: Decimal
    note: str | None
    created_by: PersonRef | None
    created_at: date


class BalanceAdjust(BaseModel):
    """Add or remove days from one member's balance."""

    leave_type_id: uuid.UUID
    days: Decimal = Field(..., ge=-365, le=365, decimal_places=1)
    note: str = Field(..., min_length=3, max_length=500)
    leave_year: int | None = Field(None, ge=2000, le=2100)

    @field_validator("days")
    @classmethod
    def _not_zero(cls, value: Decimal) -> Decimal:
        if value == 0:
            raise ValueError("Enter how many days to add or remove.")
        return value


class MemberBalances(BaseModel):
    """A member's balances and ledger for one leave year (HR / managers)."""

    user: PersonRef
    policy_name: str
    leave_year: LeaveYear
    balances: list[Balance]
    ledger: list[LedgerEntryRead]
