# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic schemas for Slack event payloads.

These provide type safety for the subset of Slack event fields we use.
Slack sends varied shapes, so we use Optional fields liberally and
don't enforce strict validation — we parse what we need and ignore the rest.
"""

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
    event: dict = Field(default_factory=dict)
