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

"""Redis-cached fast-path for ``GET /v1/setup/status``.

The wizard polls ``/v1/setup/status`` while waiting for the rest of
the bootstrap to settle. Each poll would otherwise grab a DB
connection just to read a single boolean — under high backend load
(e.g. a 20-repo bulk-onboard scan) the pool is hot enough that even
this trivial endpoint stays pending.

We cache the "setup is complete" signal in Redis under a single
well-known key. The flag has no TTL: once an org exists, the wizard
flag stays True forever (until an admin tears the org down, in which
case the legacy DB fallback handles the very next request and warms
the cache again).

The helpers degrade gracefully — every error path returns ``None`` /
no-op so a missing or flaky Redis falls back to today's DB query.
"""

from __future__ import annotations

import structlog

from app.services.redis_client import get_redis

logger = structlog.get_logger(__name__)

# Single-tenant flag — there is at most one initialised org per
# Bodhiorchard backend, so a single key suffices. The value stored
# under the key is the org slug (so the cached endpoint response can
# include it without hitting the DB at all).
SETUP_STATUS_REDIS_KEY = "setup:complete"


async def set_setup_complete(org_slug: str) -> None:
    """Mark the backend's setup flow as complete and remember the slug.

    No-op when Redis is unavailable; the next ``/v1/setup/status``
    call will fall back to the DB query and re-warm the cache once
    Redis is reachable again.
    """
    redis = await get_redis()
    if redis is None:
        return
    try:
        await redis.set(SETUP_STATUS_REDIS_KEY, org_slug)
    except Exception:
        logger.warning("redis_setup_status_set_failed", org_slug=org_slug)


async def get_setup_complete() -> str | None:
    """Return the cached org slug iff setup is marked complete.

    Returns ``None`` when the flag isn't set OR Redis is unreachable —
    callers should fall back to the DB-backed check in either case.
    """
    redis = await get_redis()
    if redis is None:
        return None
    try:
        value = await redis.get(SETUP_STATUS_REDIS_KEY)
    except Exception:
        logger.warning("redis_setup_status_get_failed")
        return None
    if value is None:
        return None
    # ``decode_responses=True`` is set on the shared client, so values
    # come back as ``str`` already; this guard catches the edge case
    # where a future bytes-mode client is wired in.
    return value if isinstance(value, str) else value.decode()
