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
"""Sets connected members' Slack status once at the start of each local day.

A 60-second tick like the daily post: each member's "today" comes from
their policy's timezone, and ``refreshed_on`` makes it once a day per
member, catching up after a restart. Slack clears statuses on its own at
their expiration, so there's nothing to undo at the end of the day.
"""

import asyncio
import uuid
from datetime import date

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.leave_policy import LeavePolicy
from app.models.slack_status_link import SlackStatusLink
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.slack_status_link import SlackStatusLinkRepository
from app.services.leave.policies import ensure_default_policy, today_for
from app.services.leave.slack_status.apply import clear, refresh
from app.services.leave.slack_status.settings import CONFIG_KEY

logger = structlog.get_logger(__name__)
TICK_SECONDS = 60


async def tick_once() -> None:
    """One pass over every org that switched status on."""
    async with AsyncSessionLocal() as db:
        orgs = await OrganizationRepository(db).list_with_slack_token_and_config()
    for org_id, _bot_token, config in orgs:
        if not ((config or {}).get(CONFIG_KEY) or {}).get("enabled"):
            continue
        try:
            async with AsyncSessionLocal() as db:
                await _org_pass(db, org_id)
        except Exception:
            logger.exception("slack_status_org_failed", org_id=str(org_id))


async def _org_pass(db: AsyncSession, org_id: uuid.UUID) -> None:
    links = await _links(db, org_id)
    if not links:
        return
    profiles = await EmployeeProfileRepository(db, org_id=org_id).by_users(
        [link.user_id for link in links]
    )
    policies = {p.id: p for p in await LeavePolicyRepository(db, org_id=org_id).list_ordered()}
    default = await ensure_default_policy(db, org_id)
    due: list[tuple[uuid.UUID, LeavePolicy, date]] = []
    for link in links:
        profile = profiles.get(link.user_id)
        policy_id = profile.leave_policy_id if profile else None
        policy = policies.get(policy_id, default) if policy_id else default
        day = today_for(policy)
        if link.refreshed_on != day:
            due.append((link.user_id, policy, day))
    for user_id, policy, day in due:
        await _member(org_id, user_id, "slack_status_member_failed", policy=policy, day=day)


async def clear_all(org_id: uuid.UUID) -> None:
    """Take our status off everyone (HR switched the feature off). Tokens are kept."""
    async with AsyncSessionLocal() as db:
        user_ids = [link.user_id for link in await _links(db, org_id)]
    for user_id in user_ids:
        await _member(org_id, user_id, "slack_status_clear_failed")


async def _links(db: AsyncSession, org_id: uuid.UUID) -> list[SlackStatusLink]:
    return await SlackStatusLinkRepository(db, org_id=org_id).all_links()


async def _member(
    org_id: uuid.UUID,
    user_id: uuid.UUID,
    failure: str,
    *,
    policy: LeavePolicy | None = None,
    day: date | None = None,
) -> None:
    """Refresh (with ``policy`` and ``day``) or clear one member, in their own session.

    Own session and own try: one member's trouble can't hold up, or expire
    the objects of, everyone after them.
    """
    try:
        async with AsyncSessionLocal() as db:
            link = await SlackStatusLinkRepository(db, org_id=org_id).for_user(user_id)
            if link is None:
                return
            if policy is not None and day is not None:
                await refresh(db, link, policy, day, enabled=True)
            else:
                await clear(db, link)
            await db.commit()
    except Exception:
        logger.exception(failure, org_id=str(org_id), user_id=str(user_id))


async def run_forever() -> None:
    """Tick every minute until cancelled."""
    while True:
        try:
            await tick_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("slack_status_tick_failed")
        await asyncio.sleep(TICK_SECONDS)
