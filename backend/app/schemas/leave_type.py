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

"""DTOs for a leave type's rules, on a policy or in the org's library."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field, field_validator, model_validator

from app.models.employee_profile import Gender
from app.models.leave_type import LeaveAccrual


class LeaveTypeRules(BaseModel):
    """A leave type's name, quota and rules: what a library entry holds."""

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
    # Refuse requests past the balance instead of making the rest loss of pay.
    stops_at_balance: bool = False
    # Carry unused days into the next leave year, up to this many; None = none.
    carry_forward_days: Decimal | None = Field(None, ge=0, le=365, decimal_places=1)
    color_key: str = Field("swatch-1", pattern=r"^swatch-[1-7]$")

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

    @field_validator("monthly_limit_days", "carry_forward_days")
    @classmethod
    def _half_days(cls, value: Decimal | None) -> Decimal | None:
        if value is not None and (value * 2) % 1:
            raise ValueError("Use whole or half days, e.g. 1 or 1.5.")
        return value

    @model_validator(mode="after")
    def _auto_needs_allowance(self) -> "LeaveTypeRules":
        # Unlimited leave that approves itself would need nobody's say at all.
        if self.auto_approve and self.annual_quota_days is None:
            raise ValueError("A type that approves itself needs a yearly allowance.")
        # Unlimited leave has no balance to stop at, or to carry over.
        if self.annual_quota_days is None:
            self.stops_at_balance = False
        if self.annual_quota_days is None or not self.carry_forward_days:
            self.carry_forward_days = None
        return self


class LeaveTypeWrite(LeaveTypeRules):
    """Create or update a policy's own leave type."""

    is_active: bool = True


class LeaveTypeRead(LeaveTypeWrite):
    """A policy's leave type, and the library entry it follows if any."""

    id: uuid.UUID
    policy_id: uuid.UUID
    template_id: uuid.UUID | None = None
    # A linked type with its own yearly quota instead of the library default.
    own_quota: bool = False
