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

"""Async Redis client singleton with graceful fallback.

Provides a lazily-initialized ``redis.asyncio`` client using the URL
from ``settings.redis.redis_url``.  If Redis is unreachable on the
first connection attempt the module remembers the failure and returns
``None`` on subsequent calls (avoiding repeated connection timeouts).

Call ``close_redis()`` during application shutdown to release the
connection pool cleanly.
"""

import structlog
from redis.asyncio import Redis

logger = structlog.get_logger(__name__)

_redis: Redis | None = None
_redis_available: bool | None = None  # None = not tested yet


async def get_redis() -> Redis | None:
    """Return the shared Redis client, or ``None`` if Redis is unavailable.

    The client is created lazily on the first call. A failed ``PING``
    sets ``_redis_available = False`` so later calls return ``None``
    immediately without re-attempting the connection.
    """
    global _redis, _redis_available  # noqa: PLW0603

    if _redis_available is False:
        return None

    if _redis is None:
        from app.config import settings

        try:
            _redis = Redis.from_url(
                settings.redis.redis_url,
                decode_responses=True,
            )
            await _redis.ping()
            _redis_available = True
            logger.info("redis_connected", url=settings.redis.redis_url)
        except Exception:
            logger.warning("redis_unavailable_using_fallback")
            _redis_available = False
            _redis = None
            return None

    return _redis


async def close_redis() -> None:
    """Shut down the Redis connection pool.

    Safe to call even if Redis was never initialised.  Resets the
    availability flag so a future ``get_redis()`` call will re-attempt
    the connection (useful for test teardown).
    """
    global _redis, _redis_available  # noqa: PLW0603

    if _redis is not None:
        await _redis.aclose()
        logger.info("redis_closed")
    _redis = None
    _redis_available = None
