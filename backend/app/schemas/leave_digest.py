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

"""DTOs for the daily who's-out Slack post."""

from pydantic import BaseModel, Field, field_validator

from app.schemas.settings import validate_optional_timezone


class LeaveDigestSettings(BaseModel):
    """Org-wide settings, stored under ``org.config["leave_digest"]``."""

    enabled: bool = False
    # A Slack channel id (C… public, G… private); the bot must be in it.
    channel_id: str = Field("", max_length=30, pattern=r"^([CG][A-Z0-9]{6,})?$")
    post_time: str = Field("09:30", pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    # None follows the default leave policy's timezone.
    timezone: str | None = Field(None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def _timezone(cls, value: str | None) -> str | None:
        return validate_optional_timezone(value)


class DigestTestResult(BaseModel):
    """What a test post did: Slack's error code if it failed, and the text."""

    ok: bool
    error: str | None
    text: str
