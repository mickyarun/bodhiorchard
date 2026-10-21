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

"""DTOs for setting people's Slack status on WFH and leave days."""

from pydantic import BaseModel, Field


class SlackStatusSettings(BaseModel):
    """HR's view; the client secret is never sent back."""

    enabled: bool = False
    client_id: str = Field("", max_length=64, pattern=r"^[0-9.]*$")
    has_client_secret: bool = False
    # The URL to add under the Slack app's OAuth "Redirect URLs".
    redirect_url: str = ""


class SlackStatusUpdate(BaseModel):
    """A save; omit ``client_secret`` to keep the saved one."""

    enabled: bool = False
    client_id: str = Field("", max_length=64, pattern=r"^[0-9.]*$")
    client_secret: str | None = Field(None, max_length=128)


class SlackStatusMine(BaseModel):
    """What the member sees: whether it's offered and whether they're connected."""

    available: bool
    connected: bool


class SlackStatusConnect(BaseModel):
    """Where to send the member to approve."""

    url: str
