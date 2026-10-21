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

"""DTOs for putting approved leave and WFH on people's Google Calendars."""

from pydantic import BaseModel, Field

HHMM = r"^([01]\d|2[0-3]):[0-5]\d$"


class CalendarSyncOptions(BaseModel):
    """What the events look like; stored under ``org.config["leave_calendar"]``."""

    enabled: bool = False
    # Out-of-office events decline new meetings that land on them.
    decline_meetings: bool = True
    decline_message: str = Field(
        "I'm out of office and will reply when I'm back.", min_length=1, max_length=300
    )
    # Where a half day splits, in the requester's policy timezone.
    midday: str = Field("13:00", pattern=HHMM)


class CalendarSyncSettings(CalendarSyncOptions):
    """Settings as HR sees them: the key itself is never sent back."""

    service_account_email: str | None = None


class CalendarSyncUpdate(CalendarSyncOptions):
    """A save. ``service_account_key`` is the downloaded JSON; omit it to keep the saved one."""

    service_account_key: str | None = Field(None, max_length=10_000)


class CalendarSyncTestResult(BaseModel):
    """Whether we could reach the caller's own calendar, and Google's error if not."""

    ok: bool
    error: str | None = None
    calendar: str | None = None
