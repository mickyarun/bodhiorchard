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

"""Celebration scheduler — one digest per org per local date.

Ticks every 60s and recomputes each org's local fire time from scratch,
so it is DST-correct and self-heals after a restart. All durable state is
the ``celebration_posts`` ledger; nothing is kept in memory between ticks.

Mirrors ``quiz_scheduler`` deliberately — same tick, same failure
backoff, same per-org isolation, so an operator who knows one knows both.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import structlog

from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.services.celebrations.poster import post_digest
from app.services.celebrations.schedule import compute_post_window, resolve_zone
from app.services.org_settings import get_celebration_settings

logger = structlog.get_logger(__name__)

TICK_SECONDS = 60
ALERT_AFTER_CONSECUTIVE_FAILURES = 3


async def tick_once() -> None:
    """One pass over every org: post any digest that is due."""
    now_utc = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        org_ids = await OrganizationRepository(session).list_all_ids()

    for org_id in org_ids:
        try:
            async with AsyncSessionLocal() as cfg_db:
                config = await OrganizationRepository(cfg_db).get_config(org_id)
            settings = get_celebration_settings(config)
            if not settings.enabled:
                continue

            window = compute_post_window(
                now_utc=now_utc,
                zone=resolve_zone(settings.timezone),
                post_time=settings.post_time,
                active_weekdays=settings.active_weekdays,
                policy=settings.weekend_policy,
            )
            if window is None:
                continue
            await post_digest(org_id, settings, window)
        except Exception:
            # One bad org must never stop the sweep for the others.
            logger.warning("celebration_scheduler_org_failed", org_id=str(org_id), exc_info=True)


async def run_forever() -> None:
    """60s tick loop — per-org timezone-aware celebration digests."""
    consecutive_failures = 0
    while True:
        try:
            await tick_once()
            consecutive_failures = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_failures += 1
            log = (
                logger.error
                if consecutive_failures >= ALERT_AFTER_CONSECUTIVE_FAILURES
                else logger.exception
            )
            log(
                "celebration_scheduler_tick_failed",
                consecutive_failures=consecutive_failures,
            )
        await asyncio.sleep(TICK_SECONDS)
