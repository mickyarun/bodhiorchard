# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tiny JSON-aware Redis cache wrapper used by GitHub-API-backed endpoints.

Wraps :func:`app.services.redis_client.get_redis` with a "fetch JSON or
fall back" pattern so call sites stay terse:

>>> data = await get_or_set_json(key, ttl=60, loader=fetch_from_github)

If Redis is unavailable, the loader is called every time — there's no
local fallback cache (deliberate: a stale local cache across reloads is
worse than the extra API call).
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from typing import Any

import structlog

from app.services.redis_client import get_redis

logger = structlog.get_logger(__name__)


async def get_or_set_json(
    key: str,
    *,
    ttl: int,
    loader: Callable[[], Awaitable[Any]],
) -> Any:
    """Return cached JSON for ``key``, or call ``loader`` and cache its result.

    Args:
        key: Redis key. Caller is responsible for namespacing.
        ttl: Cache TTL in seconds. Applied via ``SET ... EX``.
        loader: Async no-arg callable that returns a JSON-serializable
            value. Called when the key is missing or Redis is down.

    Returns:
        The cached value (decoded from JSON) or the loader's fresh result.
    """
    redis = await get_redis()
    if redis is not None:
        try:
            cached = await redis.get(key)
        except Exception:
            logger.warning("redis_cache_get_failed", key=key)
            cached = None
        if cached is not None:
            try:
                return json.loads(cached)
            except json.JSONDecodeError:
                logger.warning("redis_cache_decode_failed", key=key)

    value = await loader()
    if redis is not None:
        try:
            await redis.set(key, json.dumps(value), ex=ttl)
        except Exception:
            logger.warning("redis_cache_set_failed", key=key)
    return value
