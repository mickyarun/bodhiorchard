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

"""The ``GET /mcp/sse`` heartbeat loop: database blips, client disconnects, internal tokens.

The route function is called directly with a real Starlette request whose
``receive`` the test controls, and the token lookup answers from a script
(``valid``, ``gone`` or ``boom``), so each loop decision is pinned without a
database. The revocation paths on real rows live in the integration suite.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from starlette.requests import Request
from starlette.types import Message

from app.mcp import streamable
from app.mcp.auth import MCPAuthResult
from app.models.organization import Organization
from app.models.user_mcp_token import UserMCPToken
from tests.services.runner_internals.log_tap import LogTap

PING = b": ping\n\n"


@dataclass
class ScriptedTokens:
    """Answers the stream's token lookups from ``outcomes``, then ``gone``."""

    outcomes: Iterator[str]
    calls: int = 0
    seen: list[uuid.UUID] = field(default_factory=list)

    def repository(self, session: Any) -> ScriptedTokens:
        """Plays the ``UserMCPTokenRepository(session)`` constructor."""
        return self

    async def get_by_id(self, token_id: uuid.UUID) -> UserMCPToken | None:
        """One scripted lookup."""
        self.calls += 1
        self.seen.append(token_id)
        outcome = next(self.outcomes, "gone")
        if outcome == "boom":
            raise ConnectionError("database unavailable")
        if outcome == "expired":
            return UserMCPToken(expires_at=datetime.now(UTC) - timedelta(minutes=1))
        return UserMCPToken(expires_at=None) if outcome == "valid" else None


def _install(monkeypatch: pytest.MonkeyPatch, *outcomes: str) -> ScriptedTokens:
    tokens = ScriptedTokens(iter(outcomes))
    monkeypatch.setattr(streamable, "UserMCPTokenRepository", tokens.repository)
    monkeypatch.setattr(streamable, "_SSE_HEARTBEAT_SECONDS", 0)
    return tokens


def _request(*, disconnected: bool = False) -> Request:
    async def receive() -> Message:
        if disconnected:
            return {"type": "http.disconnect"}
        return {"type": "http.request", "body": b"", "more_body": False}

    scope = {"type": "http", "method": "GET", "path": "/mcp/sse", "headers": []}
    return Request(scope, receive)


async def _body(request: Request, token_id: uuid.UUID | None, limit: int = 50) -> bytes:
    """Collect the stream; stop after ``limit`` chunks so an endless one can't hang."""
    auth = MCPAuthResult(org=Organization(name="acme", slug="acme"), token_id=token_id)
    response = await streamable.remote_mcp_sse(request, auth)
    chunks: list[bytes] = []
    iterator = response.body_iterator

    async def collect() -> None:
        async for chunk in iterator:
            chunks.append(chunk.encode() if isinstance(chunk, str) else bytes(chunk))
            if len(chunks) >= limit:
                break

    try:
        await asyncio.wait_for(collect(), 2)
    finally:
        close = getattr(iterator, "aclose", None)
        if close is not None:
            await close()
    return b"".join(chunks)


async def test_a_single_failed_check_keeps_the_stream_alive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A blip fails open; the stream ends only when the token is gone."""
    tokens = _install(monkeypatch, "valid", "boom", "valid", "gone")
    token_id = uuid.uuid4()

    body = await _body(_request(), token_id)

    assert body.startswith(b": stream ") and body.count(PING) == 3
    assert tokens.seen == [token_id] * 4


async def test_three_failed_checks_in_a_row_close_the_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A sustained outage is capped: two fail-open beats, then the stream closes."""
    tap = LogTap()
    tap.install(monkeypatch, streamable)
    tokens = _install(monkeypatch, "boom", "boom", "boom", "valid")

    body = await _body(_request(), uuid.uuid4())

    assert (body.count(PING), tokens.calls) == (2, 3)
    failures = [r for r in tap.records if r["event"] == "mcp_remote_sse_token_check_failed"]
    assert [r["consecutive_failures"] for r in failures] == [1, 2, 3]
    assert "mcp_remote_sse_close_after_repeated_check_failures" in tap.events()


async def test_failures_separated_by_a_good_check_do_not_add_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The counter resets on success, so boom-boom-ok-boom-boom stays open."""
    _install(monkeypatch, "boom", "boom", "valid", "boom", "boom", "gone")

    body = await _body(_request(), uuid.uuid4())

    assert body.count(PING) == 5


async def test_expired_token_ends_the_stream_without_a_ping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A token already past ``expires_at`` at the first beat gets only the ready line."""
    _install(monkeypatch, "expired")

    body = await _body(_request(), uuid.uuid4())

    assert body.count(PING) == 0 and body.endswith(b" ready\n\n")


async def test_disconnected_client_stops_the_loop_before_any_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A gone client is noticed at the top of the loop; the database is not asked."""
    tokens = _install(monkeypatch, "valid")

    body = await _body(_request(disconnected=True), uuid.uuid4())

    assert (body.count(PING), tokens.calls) == (0, 0)


async def test_org_or_internal_token_stream_never_hits_the_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No per-user token id: nothing to re-check, so the beats just keep coming."""
    tokens = _install(monkeypatch)

    body = await _body(_request(), None, limit=6)

    assert (body.count(PING), tokens.calls) == (5, 0)
