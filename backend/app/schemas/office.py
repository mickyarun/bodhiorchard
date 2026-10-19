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

"""DTOs for office locations."""

import uuid

from pydantic import BaseModel, Field, field_validator

from app.schemas.country import CountryCode


class OfficeWrite(BaseModel):
    """Create or change an office."""

    name: str = Field(..., min_length=1, max_length=100)
    city: str | None = Field(None, max_length=100)
    country_code: CountryCode | None = None
    leave_policy_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Give the office a name.")
        return value.strip()

    @field_validator("city")
    @classmethod
    def _city(cls, value: str | None) -> str | None:
        return (value.strip() or None) if value is not None else None


class OfficeRead(OfficeWrite):
    """An office with its leave policy's name and how many people work there."""

    id: uuid.UUID
    leave_policy_name: str | None
    employee_count: int
