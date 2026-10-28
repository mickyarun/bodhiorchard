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

"""An in-memory ``slack.com/api`` for one workspace.

The app talks to Slack through plain ``httpx`` calls (``slack_client``,
``slack_interactive``, ``slack_user_api``), so this fake is an HTTP handler
mounted on the :class:`FakeHttpRouter`. Every Web API call is recorded as a
:class:`SlackCall` (method, merged query/body args, bearer token) and
answered from small dicts the test can fill: ``users``, ``threads``,
``presence``. A call without a token answers ``not_authed``; a token that is
not a Slack-shaped ``xox…`` string, or one listed in ``revoked_tokens``,
answers ``invalid_auth``. Profiles (``users.profile.*``) are kept per token.
``oauth.v2.access`` hands out a user token for any ``code`` except
``bad-code``. ``fail()`` makes a method answer ``{"ok": false, "error": …}``
(``missing_scope``, ``channel_not_found``…); ``rate_limit()`` answers HTTP
429 ``ratelimited`` with ``Retry-After: 0``.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from tests.fakes.http_util import FaultPlan, InjectedFault, json_response, request_json

API_HOST = "slack.com"
TEAM_ID = "T0FAKE"
BOT_USER_ID = "U0BOT"


@dataclass(frozen=True)
class SlackCall:
    """One recorded Web API call."""

    method: str
    args: dict[str, Any]
    token: str


class FakeSlack:
    """See the module docstring."""

    def __init__(self, team_id: str = TEAM_ID) -> None:
        self.team_id = team_id
        self.calls: list[SlackCall] = []
        self.users: dict[str, dict[str, Any]] = {}
        self.threads: dict[str, list[dict[str, Any]]] = {}
        self.presence: dict[str, str] = {}
        self.statuses: dict[str, dict[str, Any]] = {}
        self.revoked_tokens: set[str] = set()
        self.faults = FaultPlan()
        self._ts = itertools.count(1)
        self._ids = itertools.count(1)

    # ── test setup ────────────────────────────────────────────────
    def add_user(self, user_id: str, name: str, email: str | None = None, **extra: Any) -> None:
        """Make ``user_id`` known to ``users.info`` / ``users.list``."""
        profile = {"real_name": name, "display_name": name, "email": email, "image_192": ""}
        self.users[user_id] = {
            "id": user_id,
            "team_id": self.team_id,
            "name": name.lower(),
            "real_name": name,
            "deleted": False,
            "is_bot": False,
            "profile": profile,
            **extra,
        }

    def fail(self, method: str, error: str = "missing_scope", times: int = 1) -> None:
        """Make ``method`` answer ``ok: false`` with ``error``."""
        body = {"ok": False, "error": error}
        self.faults.add(InjectedFault("*", f"^/api/{method}$", 200, body, {}, times))

    def rate_limit(self, method: str, times: int = 1) -> None:
        """Make ``method`` answer HTTP 429 ``ratelimited``."""
        body = {"ok": False, "error": "ratelimited"}
        fault = InjectedFault("*", f"^/api/{method}$", 429, body, {"Retry-After": "0"}, times)
        self.faults.add(fault)

    # ── assertions ────────────────────────────────────────────────
    def calls_to(self, method: str) -> list[SlackCall]:
        """Recorded calls to ``method`` (e.g. ``chat.postMessage``)."""
        return [call for call in self.calls if call.method == method]

    def posted_texts(self) -> list[str]:
        """The ``text`` of every ``chat.postMessage`` call, in order."""
        return [str(call.args.get("text", "")) for call in self.calls_to("chat.postMessage")]

    # ── request handling ──────────────────────────────────────────
    def handle(self, request: httpx.Request) -> httpx.Response:
        """Serve one Web API request (mount on the router for ``slack.com``)."""
        method = request.url.path.removeprefix("/api/")
        args = {**dict(request.url.params), **request_json(request)}
        token = request.headers.get("authorization", "").removeprefix("Bearer ")
        if method == "oauth.v2.access":
            token = "basic-auth"
        self.calls.append(SlackCall(method, args, token))
        injected = self.faults.take(request)
        if injected is not None:
            return injected
        if not token:
            return json_response(200, {"ok": False, "error": "not_authed"})
        if token != "basic-auth" and (not token.startswith("xox") or token in self.revoked_tokens):
            return json_response(200, {"ok": False, "error": "invalid_auth"})
        handler = self._routes().get(method)
        body = (
            handler({**args, "_token": token})
            if handler
            else {"ok": False, "error": "unknown_method"}
        )
        return json_response(200, body)

    def _routes(self) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
        return {
            "chat.postMessage": self._post_message,
            "chat.update": lambda a: {"ok": True, "channel": a.get("channel"), "ts": a.get("ts")},
            "chat.postEphemeral": lambda a: {"ok": True, "message_ts": self._next_ts()},
            "reactions.add": lambda a: {"ok": True},
            "reactions.remove": lambda a: {"ok": True},
            "users.info": self._users_info,
            "users.list": lambda a: {"ok": True, "members": list(self.users.values())},
            "users.getPresence": lambda a: {
                "ok": True,
                "presence": self.presence.get(str(a.get("user")), "away"),
            },
            "users.profile.get": lambda a: {
                "ok": True,
                "profile": self.statuses.get(str(a["_token"]), {}),
            },
            "users.profile.set": self._set_profile,
            "conversations.open": lambda a: {"ok": True, "channel": {"id": f"D{a.get('users')}"}},
            "conversations.replies": lambda a: self._messages(str(a.get("ts"))),
            "conversations.history": lambda a: self._messages(str(a.get("channel"))),
            "views.open": lambda a: {"ok": True, "view": {"id": f"V{next(self._ids):05d}"}},
            "auth.test": lambda a: {"ok": True, "team_id": self.team_id, "user_id": BOT_USER_ID},
            "auth.revoke": self._revoke,
            "oauth.v2.access": self._oauth,
        }

    def _next_ts(self) -> str:
        return f"1700000000.{next(self._ts):06d}"

    def _post_message(self, args: dict[str, Any]) -> dict[str, Any]:
        ts = self._next_ts()
        message = {"ts": ts, "text": args.get("text", ""), "user": BOT_USER_ID}
        thread = str(args.get("thread_ts") or ts)
        self.threads.setdefault(thread, []).append(message)
        if not args.get("thread_ts"):
            self.threads.setdefault(str(args.get("channel")), []).append(message)
        return {"ok": True, "channel": args.get("channel"), "ts": ts, "message": message}

    def _users_info(self, args: dict[str, Any]) -> dict[str, Any]:
        user = self.users.get(str(args.get("user")))
        return {"ok": True, "user": user} if user else {"ok": False, "error": "user_not_found"}

    def _set_profile(self, args: dict[str, Any]) -> dict[str, Any]:
        token = str(args["_token"])
        self.statuses[token] = dict(args.get("profile") or {})
        return {"ok": True, "profile": self.statuses[token]}

    def _revoke(self, args: dict[str, Any]) -> dict[str, Any]:
        self.revoked_tokens.add(str(args["_token"]))
        return {"ok": True, "revoked": True}

    def _oauth(self, args: dict[str, Any]) -> dict[str, Any]:
        if args.get("code") == "bad-code":
            return {"ok": False, "error": "invalid_code"}
        user = {"id": "U0OAUTH", "access_token": f"xoxp-user-{next(self._ids)}"}
        return {"ok": True, "team": {"id": self.team_id}, "authed_user": user}

    def _messages(self, key: str) -> dict[str, Any]:
        return {"ok": True, "messages": list(self.threads.get(key, [])), "has_more": False}
