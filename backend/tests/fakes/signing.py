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

"""Signed inbound requests: GitHub webhooks and Slack events / interactions.

Each builder returns ``(body_bytes, headers)`` ready for
``client.post(url, content=body, headers=headers)``. The signatures are
computed exactly as GitHub (``X-Hub-Signature-256``) and Slack (``v0`` with
``X-Slack-Request-Timestamp``) compute them, so the app's real verifiers
run. Pass ``secret="wrong"`` or a stale ``timestamp`` for the negative cases.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
import uuid
from typing import Any
from urllib.parse import urlencode


def github_signature(secret: str, body: bytes) -> str:
    """``sha256=<hex>`` HMAC of ``body`` under ``secret``."""
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def signed_github_webhook(
    secret: str, event: str, payload: dict[str, Any], delivery_id: str | None = None
) -> tuple[bytes, dict[str, str]]:
    """A GitHub webhook delivery for ``event`` signed with ``secret``."""
    body = json.dumps(payload).encode()
    headers = {
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery_id or str(uuid.uuid4()),
        "X-Hub-Signature-256": github_signature(secret, body),
    }
    return body, headers


def slack_signature(secret: str, timestamp: str, body: bytes) -> str:
    """``v0=<hex>`` HMAC of ``v0:{timestamp}:{body}`` under ``secret``."""
    base = f"v0:{timestamp}:{body.decode()}".encode()
    return "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()


def _slack_headers(
    secret: str, body: bytes, timestamp: int | None, content_type: str
) -> dict[str, str]:
    ts = str(int(time.time()) if timestamp is None else timestamp)
    return {
        "Content-Type": content_type,
        "X-Slack-Request-Timestamp": ts,
        "X-Slack-Signature": slack_signature(secret, ts, body),
    }


def signed_slack_event(
    secret: str, team_id: str, event: dict[str, Any], *, timestamp: int | None = None
) -> tuple[bytes, dict[str, str]]:
    """An Events API ``event_callback`` envelope around ``event``."""
    envelope = {
        "type": "event_callback",
        "team_id": team_id,
        "event_id": f"Ev{uuid.uuid4().hex[:10].upper()}",
        "event_time": int(time.time()),
        "event": event,
    }
    body = json.dumps(envelope).encode()
    return body, _slack_headers(secret, body, timestamp, "application/json")


def signed_slack_interaction(
    secret: str, payload: dict[str, Any], *, timestamp: int | None = None
) -> tuple[bytes, dict[str, str]]:
    """A Block Kit interaction (``payload=<json>`` form body)."""
    body = urlencode({"payload": json.dumps(payload)}).encode()
    content_type = "application/x-www-form-urlencoded"
    return body, _slack_headers(secret, body, timestamp, content_type)


def signed_slack_command(
    secret: str,
    team_id: str,
    command: str,
    text: str,
    user_id: str,
    *,
    timestamp: int | None = None,
) -> tuple[bytes, dict[str, str]]:
    """A slash-command form post (for when the app grows a command route)."""
    fields = {"team_id": team_id, "command": command, "text": text, "user_id": user_id}
    body = urlencode(fields).encode()
    content_type = "application/x-www-form-urlencoded"
    return body, _slack_headers(secret, body, timestamp, content_type)
