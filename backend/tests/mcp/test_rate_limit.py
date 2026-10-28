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

"""The MCP rate limiter: per-client and per-token buckets, and failing open.

Redis is replaced by an in-memory counter with the two commands the
limiter uses, and the minute bucket is pinned so no test depends on the
wall clock.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from redis.exceptions import ConnectionError as RedisConnectionError

from app.mcp import rate_limit
from app.mcp.auth import MCPAuthResult
from tests.mcp.rate_limit_support import FakeRedis, install_fake_redis


class _BrokenRedis:
    async def incrby(self, key: str, amount: int) -> int:
        raise RedisConnectionError("connection reset")


def _request(ip: str = "198.51.100.7", forwarded: str | None = None) -> Any:
    headers = {"x-forwarded-for": forwarded} if forwarded else {}
    return MagicMock(headers=headers, client=MagicMock(host=ip))


def _user_auth() -> MCPAuthResult:
    return MCPAuthResult(org=MagicMock(id=uuid.uuid4()), user=MagicMock(id=uuid.uuid4()))


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    return install_fake_redis(monkeypatch)


async def _spend(auth: MCPAuthResult, tool: str, times: int, **req: Any) -> None:
    for _ in range(times):
        await rate_limit.enforce_rate_limit(request=_request(**req), auth=auth, tool_name=tool)


async def test_per_client_bucket_allows_exactly_sixty_units(fake_redis: FakeRedis) -> None:
    """60 unit-cost calls pass; the 61st is a 429 with Retry-After."""
    auth = _user_auth()
    await _spend(auth, "get_bud_context", 60)

    with pytest.raises(HTTPException) as exc:
        await _spend(auth, "get_bud_context", 1)

    assert exc.value.status_code == 429
    assert exc.value.headers == {"Retry-After": "60"}
    assert "this client" in exc.value.detail


async def test_expensive_tools_drain_the_bucket_faster(fake_redis: FakeRedis) -> None:
    """create_bud costs 15, so the fifth call in a minute overflows."""
    auth = _user_auth()
    await _spend(auth, "create_bud", 4)

    with pytest.raises(HTTPException):
        await _spend(auth, "create_bud", 1)


async def test_ttl_is_set_once_per_bucket(fake_redis: FakeRedis) -> None:
    """Only the first increment of a window sets the 65 s expiry."""
    auth = _user_auth()
    await _spend(auth, "get_bud_context", 3)

    assert set(fake_redis.ttls.values()) == {65}
    assert len(fake_redis.ttls) == 2  # per-client and global keys


async def test_buckets_are_separate_per_principal(fake_redis: FakeRedis) -> None:
    """One user's spend never throttles another user on the same IP."""
    await _spend(_user_auth(), "get_bud_context", 60)
    await _spend(_user_auth(), "get_bud_context", 60)


async def test_org_tokens_share_a_bucket_per_org(fake_redis: FakeRedis) -> None:
    """Org-level tokens are keyed by org, so two calls with them add up."""
    org = MagicMock(id=uuid.uuid4())
    await _spend(MCPAuthResult(org=org), "get_bud_context", 30)
    await _spend(MCPAuthResult(org=org), "get_bud_context", 30)

    with pytest.raises(HTTPException):
        await _spend(MCPAuthResult(org=org), "get_bud_context", 1)


async def test_global_cap_stops_a_token_spread_over_many_ips(fake_redis: FakeRedis) -> None:
    """Under the per-IP cap everywhere, the token still stops at 300 units."""
    auth = _user_auth()
    for n in range(5):
        await _spend(auth, "get_bud_context", 60, ip=f"203.0.113.{n}")

    with pytest.raises(HTTPException) as exc:
        await _spend(auth, "get_bud_context", 1, ip="203.0.113.99")

    assert "this token" in exc.value.detail


async def test_current_behaviour_keys_bucket_on_leftmost_forwarded_for(
    fake_redis: FakeRedis,
) -> None:
    """Describes today's keying, not an endorsement: the leftmost X-Forwarded-For wins.

    The header is client-supplied unless a proxy rewrites it, so a caller can
    pick its own per-client bucket; the per-token global cap still applies.
    Whether to trust it is an open question.
    """
    auth = _user_auth()
    await _spend(auth, "get_bud_context", 60, ip="10.0.0.1", forwarded="198.51.100.1, 10.0.0.1")
    await _spend(auth, "get_bud_context", 1, ip="10.0.0.1", forwarded="198.51.100.2")

    keys = {k for k in fake_redis.values if "_global" not in k}
    assert {k.split(":")[3] for k in keys} == {"198.51.100.1", "198.51.100.2"}


async def test_next_minute_starts_a_fresh_bucket(fake_redis: FakeRedis) -> None:
    """A client throttled this minute is allowed again in the next one."""
    auth = _user_auth()
    await _spend(auth, "get_bud_context", 60)
    with pytest.raises(HTTPException):
        await _spend(auth, "get_bud_context", 1)

    fake_redis.minute += 1
    await _spend(auth, "get_bud_context", 60)

    with pytest.raises(HTTPException):
        await _spend(auth, "get_bud_context", 1)


async def test_unknown_tool_costs_one_unit(fake_redis: FakeRedis) -> None:
    """A tool name with no weight is charged, not free."""
    await _spend(_user_auth(), "no_such_tool", 1)
    assert set(fake_redis.values.values()) == {1}


async def test_fails_open_without_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    """No redis means no throttling, not an outage."""

    async def _none() -> None:
        return None

    monkeypatch.setattr(rate_limit, "get_redis", _none)
    await _spend(_user_auth(), "create_bud", 50)


async def test_fails_open_when_redis_errors_mid_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """A redis error during the increment is swallowed and the call proceeds."""

    async def _broken() -> _BrokenRedis:
        return _BrokenRedis()

    monkeypatch.setattr(rate_limit, "get_redis", _broken)
    await _spend(_user_auth(), "create_bud", 5)
