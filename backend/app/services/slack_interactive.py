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

"""Slack Web API calls for interactive messages: blocks, updates, modals.

Kept apart from :mod:`app.services.slack_client` (plain text messages and
reads). Every call returns Slack's error code on failure instead of
raising, so a Slack outage never breaks the action that triggered it.
"""

from typing import Any, cast

import httpx
import structlog

logger = structlog.get_logger(__name__)

_SLACK_BASE = "https://slack.com/api"
_TIMEOUT = 10.0

Blocks = list[dict[str, Any]]


async def _call(token: str, method: str, payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """POST a Web API method; returns ``(data, error)`` with error "" on success."""
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{_SLACK_BASE}/{method}",
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
                timeout=_TIMEOUT,
            )
        data = cast(dict[str, Any], resp.json())
    except (httpx.HTTPError, ValueError):
        logger.warning("slack_call_failed", method=method, exc_info=True)
        return {}, "request_failed"
    if not data.get("ok"):
        error = str(data.get("error") or "unknown_error")
        logger.warning("slack_call_error", method=method, error=error)
        return data, error
    return data, ""


async def post_message(
    token: str, channel: str, text: str, blocks: Blocks | None = None
) -> tuple[str, str, str]:
    """Post a message; returns ``(channel, ts, error)``."""
    payload: dict[str, Any] = {"channel": channel, "text": text, "unfurl_links": False}
    if blocks is not None:
        payload["blocks"] = blocks
    data, error = await _call(token, "chat.postMessage", payload)
    return str(data.get("channel") or ""), str(data.get("ts") or ""), error


async def update_message(token: str, channel: str, ts: str, text: str, blocks: Blocks) -> str:
    """Replace a message's text and blocks; returns the error code or ""."""
    payload = {"channel": channel, "ts": ts, "text": text, "blocks": blocks}
    return (await _call(token, "chat.update", payload))[1]


async def post_ephemeral(token: str, channel: str, user: str, text: str) -> str:
    """Show a message only ``user`` can see; returns the error code or ""."""
    payload = {"channel": channel, "user": user, "text": text}
    return (await _call(token, "chat.postEphemeral", payload))[1]


async def open_view(token: str, trigger_id: str, view: dict[str, Any]) -> str:
    """Open a modal from a button click's trigger; returns the error code or ""."""
    return (await _call(token, "views.open", {"trigger_id": trigger_id, "view": view}))[1]
