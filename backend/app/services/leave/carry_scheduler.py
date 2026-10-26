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

"""Carries unused leave into each new leave year, checked every hour.

Each pass asks every org which of its policies started a leave year this
week (:func:`app.services.leave.carry_rule.due_year`); the carry itself is
written at most once per person, type and year, so repeated passes and a
restart mid-week are harmless.
"""

import asyncio

import structlog

from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.services.leave.carry_forward import carry_forward_org

logger = structlog.get_logger(__name__)
TICK_SECONDS = 3600


async def tick_once() -> None:
    """One pass over every org, each in its own transaction."""
    async with AsyncSessionLocal() as db:
        org_ids = await OrganizationRepository(db).list_all_ids()
    for org_id in org_ids:
        try:
            async with AsyncSessionLocal() as db:
                written = await carry_forward_org(db, org_id)
                await db.commit()
        except Exception:
            logger.exception("leave_carry_forward_org_failed", org_id=str(org_id))
            continue
        if written:
            logger.info("leave_carried_forward", org_id=str(org_id), entries=written)


async def run_forever() -> None:
    """Tick every hour until cancelled."""
    while True:
        try:
            await tick_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("leave_carry_forward_tick_failed")
        await asyncio.sleep(TICK_SECONDS)
