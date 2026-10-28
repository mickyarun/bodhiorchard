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

"""Drive the remote MCP ``GET /mcp/sse`` stream through the real route.

The test client's ASGI transport hands back the body only once the stream
ends, so a test opens the stream as a task, waits until the heartbeat has
re-checked the token a given number of times (:class:`TokenChecks` counts
the checks the stream makes through the real repository), changes the
world, and then collects the whole body.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field

import httpx
import pytest
from httpx import AsyncClient

from app.mcp import streamable
from app.models.user_mcp_token import UserMCPToken
from app.repositories.user_mcp_token import UserMCPTokenRepository

PING = ": ping\n\n"


@dataclass
class TokenChecks:
    """Counts the stream's per-heartbeat token lookups."""

    count: int = 0
    changed: asyncio.Condition = field(default_factory=asyncio.Condition)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Swap the stream's repository for a counting subclass of the real one."""
        checks = self

        class CountingRepo(UserMCPTokenRepository):
            async def get_by_id(self, entity_id: uuid.UUID) -> UserMCPToken | None:
                row = await super().get_by_id(entity_id)
                async with checks.changed:
                    checks.count += 1
                    checks.changed.notify_all()
                return row

        monkeypatch.setattr(streamable, "UserMCPTokenRepository", CountingRepo)
        monkeypatch.setattr(streamable, "_SSE_HEARTBEAT_SECONDS", 0.01)

    async def reach(self, count: int, timeout: float = 3.0) -> None:
        """Wait until the stream has checked the token ``count`` times."""
        async with self.changed:
            await asyncio.wait_for(self.changed.wait_for(lambda: self.count >= count), timeout)


async def mint_token(client: AsyncClient, headers: dict[str, str]) -> tuple[str, uuid.UUID]:
    """Mint a per-user token over HTTP; return the plaintext and its row id."""
    name = f"desktop-{uuid.uuid4().hex[:6]}"
    created = await client.post("/api/v1/me/mcp-tokens", json={"name": name}, headers=headers)
    assert created.status_code == 201, created.text
    listed = await client.get("/api/v1/me/mcp-tokens", headers=headers)
    (row,) = [t for t in listed.json() if t["name"] == name]
    return created.json()["mcp_token"], uuid.UUID(row["id"])


def open_stream(client: AsyncClient, token: str) -> asyncio.Task[httpx.Response]:
    """Start ``GET /mcp/sse`` with ``token``; the task ends when the stream closes."""
    headers = {"Authorization": f"Bearer {token}"}
    return asyncio.create_task(client.get("/mcp/sse", headers=headers))


async def closed_body(stream: asyncio.Task[httpx.Response], timeout: float = 3.0) -> str:
    """The full body of a stream that is expected to close by itself."""
    response = await asyncio.wait_for(stream, timeout)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    return response.text
