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

"""Pydantic schemas for Slack event payloads.

These provide type safety for the subset of Slack event fields we use.
Slack sends varied shapes, so we use Optional fields liberally and
don't enforce strict validation — we parse what we need and ignore the rest.
"""

from typing import Any

from pydantic import BaseModel, Field


class SlackEventItem(BaseModel):
    """The item a reaction was added to (message, file, etc.)."""

    type: str = ""
    channel: str = ""
    ts: str = ""


class SlackReactionEvent(BaseModel):
    """Payload for reaction_added / reaction_removed events."""

    type: str = ""
    user: str = ""
    reaction: str = ""
    item: SlackEventItem = Field(default_factory=SlackEventItem)
    item_user: str = ""
    event_ts: str = ""


class SlackMessageEvent(BaseModel):
    """Payload for message events (channel messages and thread replies)."""

    type: str = ""
    subtype: str | None = None
    user: str | None = None
    bot_id: str | None = None
    text: str = ""
    ts: str = ""
    thread_ts: str | None = None
    channel: str = ""
    channel_type: str | None = None
    event_ts: str = ""


class SlackEventWrapper(BaseModel):
    """Top-level wrapper for Slack Events API payloads.

    Slack sends two types of payloads:
    1. url_verification (challenge handshake) — has `challenge` field
    2. event_callback — has `event` dict with the actual event data
    """

    type: str = ""
    token: str = ""
    challenge: str | None = None
    team_id: str = ""
    event_id: str = ""
    event_time: int = 0
    event: dict[str, Any] = Field(default_factory=dict)
