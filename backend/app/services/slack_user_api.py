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
"""Slack calls made with a member's own user token (their status), and the
OAuth exchange that gets one.

Slack answers HTTP 200 with ``ok: false`` on errors; those come back as
:class:`SlackUserApiError` with Slack's error code (e.g. ``token_revoked``).
"""

import contextlib
from dataclasses import dataclass
from typing import Any

import httpx

BASE = "https://slack.com/api"
AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
USER_SCOPES = "users.profile:read,users.profile:write"
HTTP_TIMEOUT_SECONDS = 15


class SlackUserApiError(Exception):
    """Slack said no; ``code`` is its error string."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class SlackStatus:
    """A member's status as Slack shows it; expiration 0 = never."""

    text: str
    emoji: str
    expiration: int


@dataclass(frozen=True)
class UserGrant:
    """What the OAuth exchange returns for the person who approved."""

    slack_user_id: str
    token: str
    team_id: str


def _json(response: httpx.Response) -> dict[str, Any]:
    """Slack's JSON body; an HTML error page (a 5xx) reads as ``bad_response``."""
    try:
        body = response.json()
    except ValueError as exc:
        raise SlackUserApiError("bad_response") from exc
    if not isinstance(body, dict):
        raise SlackUserApiError("bad_response")
    return body


async def _call(method: str, *, token: str, **data: Any) -> dict[str, Any]:
    if not token:
        raise SlackUserApiError("not_authed")
    headers = {"Authorization": f"Bearer {token}"}
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(f"{BASE}/{method}", headers=headers, json=data or None)
    body = _json(response)
    if not body.get("ok"):
        raise SlackUserApiError(str(body.get("error", response.status_code)))
    return body


async def exchange_code(client_id: str, client_secret: str, code: str, redirect: str) -> UserGrant:
    """Trade the OAuth ``code`` for the approving member's user token.

    Refused when the Slack app rotates tokens: they'd die in 12 hours and
    we don't keep refresh tokens.
    """
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT_SECONDS) as client:
        response = await client.post(
            f"{BASE}/oauth.v2.access",
            data={"code": code, "redirect_uri": redirect},
            auth=(client_id, client_secret),
        )
    body = _json(response)
    user = body.get("authed_user") or {}
    if not body.get("ok") or not user.get("access_token"):
        raise SlackUserApiError(str(body.get("error", "no_user_token")))
    if user.get("refresh_token"):
        with contextlib.suppress(SlackUserApiError, httpx.HTTPError):
            await revoke(str(user["access_token"]))
        raise SlackUserApiError("token_rotation_on")
    # Enterprise Grid: the enterprise, whose members share one status everywhere.
    team = body.get("enterprise") or body.get("team") or {}
    return UserGrant(str(user["id"]), str(user["access_token"]), str(team.get("id", "")))


async def get_status(token: str) -> SlackStatus:
    """The member's current status."""
    profile = (await _call("users.profile.get", token=token)).get("profile") or {}
    return SlackStatus(
        text=str(profile.get("status_text", "")),
        emoji=str(profile.get("status_emoji", "")),
        expiration=int(profile.get("status_expiration") or 0),
    )


async def set_status(token: str, status: SlackStatus) -> None:
    """Set (or, with empty text and emoji, clear) the member's status."""
    profile = {
        "status_text": status.text,
        "status_emoji": status.emoji,
        "status_expiration": status.expiration,
    }
    await _call("users.profile.set", token=token, profile=profile)


async def revoke(token: str) -> None:
    """Give the token back to Slack (on disconnect)."""
    await _call("auth.revoke", token=token)
