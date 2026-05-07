# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the Redis setup-status fast-path.

The helpers degrade silently when Redis is unavailable, and the
``/v1/setup/status`` handler must short-circuit the DB query when the
flag is set. These tests cover both shapes with an in-memory fake.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.api.v1 import setup as setup_api
from app.services import redis_setup_status


class _FakeRedis:
    """Minimal in-memory stand-in for ``redis.asyncio.Redis``."""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str) -> None:
        self.store[key] = value

    async def get(self, key: str) -> str | None:
        return self.store.get(key)


@pytest.mark.asyncio
async def test_set_and_get_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    """Storing then reading the slug yields the same value."""
    fake = _FakeRedis()

    async def _fake_get_redis() -> _FakeRedis:
        return fake

    monkeypatch.setattr(redis_setup_status, "get_redis", _fake_get_redis)

    assert await redis_setup_status.get_setup_complete() is None
    await redis_setup_status.set_setup_complete("acme")
    assert await redis_setup_status.get_setup_complete() == "acme"
    assert fake.store[redis_setup_status.SETUP_STATUS_REDIS_KEY] == "acme"


@pytest.mark.asyncio
async def test_helpers_degrade_when_redis_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``get_redis`` returns ``None``, helpers no-op rather than raise."""

    async def _no_redis() -> None:
        return None

    monkeypatch.setattr(redis_setup_status, "get_redis", _no_redis)

    # Neither call raises; ``get`` returns ``None``.
    await redis_setup_status.set_setup_complete("acme")
    assert await redis_setup_status.get_setup_complete() is None


@pytest.mark.asyncio
async def test_setup_status_uses_cache_when_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """The endpoint short-circuits the DB query when the cache is warm."""
    db_hits: list[str] = []

    class _StubOrgRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def check_setup_exists(self) -> Any:
            db_hits.append("hit")
            raise AssertionError("DB should not be queried when cache is warm")

    async def _fake_get_complete() -> str:
        return "acme"

    async def _noop_set(_slug: str) -> None:
        return None

    monkeypatch.setattr(setup_api, "OrganizationRepository", _StubOrgRepo)
    monkeypatch.setattr(setup_api, "get_setup_complete", _fake_get_complete)
    monkeypatch.setattr(setup_api, "set_setup_complete", _noop_set)

    result = await setup_api.setup_status(db=None)  # type: ignore[arg-type]

    assert result == {"is_setup_complete": True, "org_slug": "acme"}
    assert db_hits == []


@pytest.mark.asyncio
async def test_setup_status_falls_back_and_warms_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the cache is empty, the DB is queried and the cache is written."""

    class _Org:
        slug = "acme"

    class _StubOrgRepo:
        def __init__(self, _db: Any) -> None:
            pass

        async def check_setup_exists(self) -> _Org:
            return _Org()

    async def _empty_cache() -> None:
        return None

    written: list[str] = []

    async def _capture_set(slug: str) -> None:
        written.append(slug)

    monkeypatch.setattr(setup_api, "OrganizationRepository", _StubOrgRepo)
    monkeypatch.setattr(setup_api, "get_setup_complete", _empty_cache)
    monkeypatch.setattr(setup_api, "set_setup_complete", _capture_set)

    result = await setup_api.setup_status(db=None)  # type: ignore[arg-type]

    assert result == {"is_setup_complete": True, "org_slug": "acme"}
    assert written == ["acme"]
