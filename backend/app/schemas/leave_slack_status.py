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

from typing import Literal

from pydantic import BaseModel, Field

# How finishing a connect went; the Leave page explains each one.
ConnectOutcome = Literal[
    "connected",
    "moved",
    "expired",
    "not_yours",
    "wrong_account",
    "unlinkable",
    "rotation",
    "failed",
]


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
    """What the member sees: offered? connected? and is a Slack account linked
    to them yet (if not, connecting links the one they approve with, when its
    email matches theirs)?"""

    available: bool
    connected: bool
    linked: bool


class SlackStatusConnect(BaseModel):
    """Where to send the member to approve."""

    url: str


class SlackStatusFinish(BaseModel):
    """What Slack sent back, handed on by the Leave page while signed in."""

    code: str = Field(min_length=1, max_length=512)
    state: str = Field(min_length=1, max_length=2048)


class SlackStatusFinished(BaseModel):
    """How it went."""

    outcome: ConnectOutcome
