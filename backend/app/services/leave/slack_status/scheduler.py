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

A 60-second tick like the daily post. Orgs that switched status on get it
set (a bot token isn't needed: members connect with their own). Each
member's "today" comes from their policy's timezone, and ``refreshed_on``
makes it once a day per member, catching up after a restart. Slack clears
statuses on its own at their expiration, so there's nothing to undo at
the end of the day.

Every org holding tokens, on or off, has people who left cleared and
forgotten on the next tick, so an ex-member's token isn't kept.
"""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import date
from functools import partial

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.leave_policy import LeavePolicy
from app.models.slack_status_link import SlackStatusLink
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.slack_status_accounts import SlackStatusAccountRepository
from app.repositories.slack_status_link import SlackStatusLinkRepository
from app.services.leave.policies import ensure_default_policy, today_for
from app.services.leave.slack_status.apply import clear, forget, hand_back, refresh

logger = structlog.get_logger(__name__)
TICK_SECONDS = 60

# Does its work in the session; returns a token to hand back after the commit.
Action = Callable[[AsyncSession, SlackStatusLink], Awaitable[str | None]]


async def tick_once() -> None:
    """One pass over every org that switched status on or holds tokens."""
    async with AsyncSessionLocal() as db:
        accounts = SlackStatusAccountRepository(db)
        on = set(await accounts.orgs_with_status_on())
        holding = set(await accounts.orgs_with_links())
    for org_id in on | holding:
        try:
            await _org_pass(org_id, enabled=org_id in on)
        except Exception:
            logger.exception("slack_status_org_failed", org_id=str(org_id))


async def _org_pass(org_id: uuid.UUID, *, enabled: bool) -> None:
    async with AsyncSessionLocal() as db:
        links = SlackStatusLinkRepository(db, org_id=org_id)
        departed = [link.user_id for link in await links.departed_links()]
        due = await _due_today(db, org_id, await links.all_links()) if enabled else []
    for user_id in departed:
        await _member(org_id, user_id, _forget_departed, "slack_status_forget_failed")
    for user_id, policy, day in due:
        set_today = partial(_set_today, policy=policy, day=day)
        await _member(org_id, user_id, set_today, "slack_status_member_failed")


async def _set_today(
    db: AsyncSession, link: SlackStatusLink, *, policy: LeavePolicy, day: date
) -> str | None:
    await refresh(db, link, policy, day, enabled=True)
    return None


async def _forget_departed(db: AsyncSession, link: SlackStatusLink) -> str | None:
    # Slack unreachable: keep the link, so next tick clears the status.
    return await forget(db, link, keep_to_retry=True)


async def _clear(db: AsyncSession, link: SlackStatusLink) -> str | None:
    await clear(db, link)
    return None


async def _due_today(
    db: AsyncSession, org_id: uuid.UUID, links: list[SlackStatusLink]
) -> list[tuple[uuid.UUID, LeavePolicy, date]]:
    """Members not yet set for their local today, with their policy and that date."""
    if not links:
        return []
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
    return due


async def clear_all(org_id: uuid.UUID) -> None:
    """Take our status off everyone (HR switched the feature off). Tokens are kept."""
    async with AsyncSessionLocal() as db:
        repo = SlackStatusLinkRepository(db, org_id=org_id)
        user_ids = [link.user_id for link in await repo.all_links()]
    for user_id in user_ids:
        await _member(org_id, user_id, _clear, "slack_status_clear_failed")


async def _member(org_id: uuid.UUID, user_id: uuid.UUID, action: Action, failure: str) -> None:
    """Run ``action`` for one member in their own session and their own try.

    One member's trouble can't hold up, or expire the objects of, anyone else.
    """
    try:
        async with AsyncSessionLocal() as db:
            link = await SlackStatusLinkRepository(db, org_id=org_id).for_user(user_id)
            if link is None:
                return
            token = await action(db, link)
            await db.commit()
        if token:
            await hand_back([token])
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
