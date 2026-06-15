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

"""Pydantic schemas for the self-service notification preference endpoints."""

from pydantic import BaseModel, Field


class NotificationPreferenceItem(BaseModel):
    """One togglable notification category, resolved for the current member.

    Combines the static registry metadata (``key``/``label``/``description``/
    ``group``) with this member's effective ``enabled`` state, so the profile
    UI can render the full list without a second lookup.
    """

    key: str
    label: str
    description: str
    group: str
    enabled: bool


class NotificationPreferencesRead(BaseModel):
    """GET response — every category plus the member's current choice."""

    items: list[NotificationPreferenceItem]


class NotificationPreferencesUpdate(BaseModel):
    """PATCH body — a partial map of ``category_key -> enabled``.

    Partial by design: the UI sends only the toggles that changed. Unknown
    keys are rejected by the handler (against the registry) so stale clients
    can't persist categories no sender will ever read.
    """

    preferences: dict[str, bool] = Field(
        ..., description="Map of notification category key to enabled flag."
    )
