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

"""Periodic retention sweep for ``mcp_audit_log``.

Mirrors the in-process loop pattern used by ``presence_cache.refresh_all_presence``:
a single asyncio task spawned at app startup runs the sweep once a day.
Single-instance assumption — if Bodhiorchard grows multi-instance we'll
add a Redis lock to avoid duplicate deletes from each pod.
"""

import asyncio
from datetime import UTC, datetime, timedelta

import structlog

from app.database import AsyncSessionLocal
from app.repositories.mcp_audit_log import MCPAuditLogRepository

logger = structlog.get_logger(__name__)

RETENTION_DAYS = 90
SLEEP_SECONDS = 24 * 60 * 60  # daily on success
RETRY_SLEEP_SECONDS = 60 * 60  # hourly while the sweep is failing
# After this many consecutive failures the table is silently growing.
# Escalate log level so operators see it on dashboards / Sentry, not just
# in the per-failure exception noise.
ALERT_AFTER_CONSECUTIVE_FAILURES = 2


async def sweep_once() -> int:
    """Run one retention pass. Returns the number of rows deleted."""
    cutoff = datetime.now(UTC) - timedelta(days=RETENTION_DAYS)
    async with AsyncSessionLocal() as session:
        deleted = await MCPAuditLogRepository(session).delete_older_than(cutoff)
        await session.commit()
    if deleted:
        logger.info("mcp_audit_retention_swept", deleted=deleted, cutoff=cutoff.isoformat())
    return deleted


async def run_forever() -> None:
    """Daily loop with consecutive-failure backoff.

    On success: sleep for the full 24h window. On failure: retry hourly so
    a broken sweep doesn't let the audit table grow unbounded for a full
    day per attempt. Escalates to ERROR after a few consecutive failures
    so the situation surfaces on alerting dashboards.
    """
    consecutive_failures = 0
    while True:
        try:
            await sweep_once()
            consecutive_failures = 0
            sleep_for = SLEEP_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_failures += 1
            log = (
                logger.error
                if consecutive_failures >= ALERT_AFTER_CONSECUTIVE_FAILURES
                else logger.exception
            )
            log("mcp_audit_retention_failed", consecutive_failures=consecutive_failures)
            sleep_for = RETRY_SLEEP_SECONDS
        await asyncio.sleep(sleep_for)
