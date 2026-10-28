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

"""An in-memory redis and a hand-moved clock for the MCP rate limiter.

:func:`install_fake_redis` swaps ``get_redis`` for a dict-backed stand-in
with the two commands the limiter uses, and replaces the minute bucket with
a counter the test advances itself, so nothing depends on the wall clock.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from app.mcp import rate_limit


@dataclass
class FakeRedis:
    """``INCRBY`` / ``EXPIRE`` over a dict, recording TTLs, plus the current minute."""

    values: dict[str, int] = field(default_factory=dict)
    ttls: dict[str, int] = field(default_factory=dict)
    minute: int = 29_000_000

    async def incrby(self, key: str, amount: int) -> int:
        """Add ``amount`` to ``key`` and return the new total."""
        self.values[key] = self.values.get(key, 0) + amount
        return self.values[key]

    async def expire(self, key: str, seconds: int) -> bool:
        """Record the TTL the limiter asked for."""
        self.ttls[key] = seconds
        return True


def install_fake_redis(monkeypatch: pytest.MonkeyPatch) -> FakeRedis:
    """Point the limiter at a fresh :class:`FakeRedis` and its minute counter."""
    redis = FakeRedis()

    async def _get() -> FakeRedis:
        return redis

    monkeypatch.setattr(rate_limit, "get_redis", _get)
    monkeypatch.setattr(rate_limit, "_bucket_minute", lambda: redis.minute)
    return redis
