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

"""``post_message_outcome`` must tell "never sent" apart from "maybe sent".

The celebration poster retries only the former; retrying the latter could
post twice to a whole channel.
"""

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from app.services import slack_client


def _patch_transport(
    monkeypatch: pytest.MonkeyPatch, handler: Callable[[httpx.Request], httpx.Response]
) -> None:
    real = httpx.AsyncClient

    def _client(*args: Any, **kwargs: Any) -> httpx.AsyncClient:
        return real(transport=httpx.MockTransport(handler))

    monkeypatch.setattr(slack_client.httpx, "AsyncClient", _client)


def _raise(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        raise exc

    return handler


async def _post() -> slack_client.PostOutcome:
    return await slack_client.post_message_outcome(
        "xoxb", "C1", "hi", blocks=[{"type": "divider"}]
    )


async def test_ok(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, lambda r: httpx.Response(200, json={"ok": True, "ts": "1.1"}))
    outcome = await _post()
    assert outcome.ok and outcome.ts == "1.1" and outcome.error is None


async def test_blocks_are_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = request.read()
        return httpx.Response(200, json={"ok": True, "ts": "1"})

    _patch_transport(monkeypatch, handler)
    await _post()
    assert b'"blocks"' in seen["body"]


async def test_slack_error_is_definite(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(
        monkeypatch, lambda r: httpx.Response(200, json={"ok": False, "error": "not_in_channel"})
    )
    outcome = await _post()
    assert not outcome.ok
    assert outcome.error == "not_in_channel"
    assert not outcome.maybe_delivered


async def test_5xx_may_have_been_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    # Slack can error after accepting a message; retrying could double-post.
    _patch_transport(monkeypatch, lambda r: httpx.Response(503, text="<html>down</html>"))
    outcome = await _post()
    assert outcome.error == "http_503"
    assert outcome.maybe_delivered


async def test_non_json_body_does_not_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, lambda r: httpx.Response(200, text="not json"))
    outcome = await _post()
    assert not outcome.ok and outcome.error == "http_200_non_json"


async def test_connect_error_was_never_sent(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, _raise(httpx.ConnectError("refused")))
    outcome = await _post()
    assert not outcome.ok
    assert not outcome.maybe_delivered


async def test_read_timeout_may_have_been_delivered(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_transport(monkeypatch, _raise(httpx.ReadTimeout("slow")))
    outcome = await _post()
    assert not outcome.ok
    assert outcome.maybe_delivered
    assert outcome.error == "ReadTimeout"
