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

"""Daily roll-forward of the 30-day baseline snapshot on velocity_aggregates.

The Learnings overview's ``trend_30d_pct`` field compares each bucket's
current ``running_mean`` against the value stored in
``running_mean_30d_ago``. This module advances that baseline once a
day: any bucket whose snapshot is older than ``SNAPSHOT_AGE_HOURS``
(or has never been snapshotted) gets the current running_mean copied
into the 30d_ago slot.

Single-instance assumption mirrors ``mcp_audit_cleanup`` — when
Bodhiorchard grows multi-instance we'll add a Redis lock so two pods
don't double-roll.
"""

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.organization import Organization
from app.repositories.velocity_aggregate import VelocityAggregateRepository

logger = structlog.get_logger(__name__)

SNAPSHOT_AGE_HOURS = 24
SLEEP_SECONDS = 24 * 60 * 60
RETRY_SLEEP_SECONDS = 60 * 60
ALERT_AFTER_CONSECUTIVE_FAILURES = 2


async def _roll_org(org_id: uuid.UUID) -> int:
    """Roll buckets due for a snapshot in one org. Returns rows updated."""
    rolled = 0
    async with AsyncSessionLocal() as session:
        repo = VelocityAggregateRepository(session, org_id=org_id)
        due = await repo.list_buckets_due_for_30d_snapshot(
            threshold_seconds=SNAPSHOT_AGE_HOURS * 3600,
        )
        now = datetime.now(tz=UTC)
        for bucket in due:
            await repo.write_30d_snapshot(
                bucket.id,
                running_mean_30d_ago=(
                    float(bucket.running_mean) if bucket.running_mean is not None else None
                ),
                snapshot_taken_at=now,
            )
            rolled += 1
        await session.commit()
    return rolled


async def sweep_once() -> int:
    """Roll every org once. Returns total rows updated across orgs."""
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Organization.id))
        org_ids = [row[0] for row in result.all()]

    total = 0
    for oid in org_ids:
        try:
            total += await _roll_org(oid)
        except Exception:
            logger.warning("velocity_snapshot_org_failed", org_id=str(oid), exc_info=True)
    if total:
        logger.info("velocity_snapshot_rolled", rows=total, orgs=len(org_ids))
    return total


async def run_forever() -> None:
    """Daily loop, identical structure to ``mcp_audit_cleanup.run_forever``."""
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
            log("velocity_snapshot_failed", consecutive_failures=consecutive_failures)
            sleep_for = RETRY_SLEEP_SECONDS
        await asyncio.sleep(sleep_for)
