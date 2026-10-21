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

"""Query filters for leave reports, one model per report.

Each report validates only the filters it uses, so none are silently ignored.
"""

import uuid
from datetime import date, timedelta

from pydantic import BaseModel, Field, model_validator

from app.models.leave_request import LeaveKind, LeaveStatus

MAX_RANGE = timedelta(days=366)
# The leave years the other leave endpoints accept; dates outside them would
# overflow the calendar maths (a leave year ends in the following year).
FIRST_YEAR, LAST_YEAR = 2000, 2100


class PeopleFilters(BaseModel):
    """Who to report on, within what the viewer may see."""

    user_id: uuid.UUID | None = None
    department: str | None = None
    office_id: uuid.UUID | None = None
    # The member's current policy (for the register: the policy a request was priced on).
    policy_id: uuid.UUID | None = None
    # Members who list this person as a reporting manager.
    manager_id: uuid.UUID | None = None


class RangeFilters(PeopleFilters):
    """A date range of at most a year."""

    start: date
    end: date

    @model_validator(mode="after")
    def _range(self) -> "RangeFilters":
        if self.end < self.start:
            raise ValueError("The end date must be on or after the start date.")
        if self.end - self.start >= MAX_RANGE:
            raise ValueError("Pick a range of a year or less.")
        if self.start.year < FIRST_YEAR or self.end.year > LAST_YEAR:
            raise ValueError(f"Pick dates between {FIRST_YEAR} and {LAST_YEAR}.")
        return self


class SummaryFilters(RangeFilters):
    """Employee-wise leave taken in a range."""


class RegisterFilters(RangeFilters):
    """Every request overlapping a range."""

    kind: LeaveKind | None = None
    leave_type_id: uuid.UUID | None = None
    status: LeaveStatus | None = None


class BalanceFilters(PeopleFilters):
    """Balances for a leave year (each member's own policy's year)."""

    year: int | None = Field(None, ge=FIRST_YEAR, le=LAST_YEAR)
