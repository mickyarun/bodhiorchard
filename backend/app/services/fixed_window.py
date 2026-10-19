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

"""A per-key counter over fixed time windows, for simple throttles.

Fails open: if Redis is missing or errors, the action is allowed and a
warning logged. A cache blip must never stop someone requesting leave.
"""

import time

import structlog
from redis.exceptions import RedisError

from app.services.redis_client import get_redis

logger = structlog.get_logger(__name__)


async def seconds_until_allowed(key: str, *, limit: int, window_seconds: int) -> int:
    """Count one attempt for ``key``; 0 if it's within ``limit`` this window,
    else the seconds until the window resets (for Retry-After)."""
    now = time.time()
    bucket = int(now // window_seconds)
    redis_key = f"throttle:{key}:{bucket}"
    redis = await get_redis()
    if redis is None:
        logger.warning("throttle_redis_unavailable", key=key)
        return 0
    try:
        hits = await redis.incr(redis_key)
        if hits == 1:
            await redis.expire(redis_key, window_seconds + 5)
    except RedisError:
        logger.warning("throttle_redis_error", key=key, exc_info=True)
        return 0
    if int(hits) <= limit:
        return 0
    return max(1, int((bucket + 1) * window_seconds - now))
