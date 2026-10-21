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
"""Set a connected member's Slack status for today.

Called right after a request changes (so approving today's WFH shows at
once) and by the daily pass. With the feature switched off it only ever
clears our own status, so cancelled leave doesn't linger.

Best effort. A token that can't work again is forgotten; rate limits and
network errors are retried next pass; anything else waits for tomorrow,
so one broken account isn't retried (and logged) every minute.
"""

import contextlib
import uuid
from collections.abc import Iterable
from datetime import UTC, date, datetime, time, timedelta

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.encryption import decrypt_secret
from app.database import AsyncSessionLocal
from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveStatus
from app.models.slack_status_link import SlackStatusLink
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.slack_status_link import SlackStatusLinkRepository
from app.services.leave.calendar_sync.settings import load_options
from app.services.leave.policies import resolve_member_policy, today_for
from app.services.leave.slack_status.plan import (
    NO_STATUS,
    Booking,
    change_needed,
    status_for,
)
from app.services.leave.slack_status.settings import load_client
from app.services.quiz_schedule_math import resolve_zone
from app.services.slack_user_api import (
    SlackStatus,
    SlackUserApiError,
    get_status,
    revoke,
    set_status,
)

logger = structlog.get_logger(__name__)
# Slack's answers for a token that will never work again.
DEAD_TOKEN = {
    "token_revoked",
    "token_expired",
    "invalid_auth",
    "not_authed",
    "account_inactive",
    "missing_scope",
}
_RETRY_SOON = {"ratelimited", "bad_response"}


async def refresh_after_change(org_id: uuid.UUID, request_id: uuid.UUID) -> None:
    """After a request changes, bring its owner's status up to date (background)."""
    async with AsyncSessionLocal() as db:
        request = await LeaveRequestRepository(db, org_id=org_id).get_by_id(request_id)
    if request is not None:
        await refresh_member(org_id, request.user_id)


async def refresh_member(org_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Set one member's status for their today, if they connected (background)."""
    async with AsyncSessionLocal() as db:
        link = await SlackStatusLinkRepository(db, org_id=org_id).for_user(user_id)
        if link is None:
            return
        enabled = (await load_client(db, org_id)).enabled
        policy = (await resolve_member_policy(db, org_id, user_id)).policy
        await refresh(db, link, policy, today_for(policy), enabled=enabled)
        await db.commit()


async def refresh(
    db: AsyncSession, link: SlackStatusLink, policy: LeavePolicy, day: date, *, enabled: bool
) -> None:
    """Set ``link``'s member's status for ``day`` (their local date) and note it."""
    wanted = await _wanted(db, link, policy, day) if enabled else NO_STATUS
    next_midnight = datetime.combine(
        day + timedelta(days=1), time(0), resolve_zone(policy.timezone)
    )
    await _put(db, link, wanted, next_midnight)


async def clear(db: AsyncSession, link: SlackStatusLink) -> bool:
    """Take our status off (feature switched off); False if Slack should be retried."""
    return await _put(db, link, NO_STATUS, None)


async def forget(db: AsyncSession, link: SlackStatusLink, *, keep_to_retry: bool) -> str | None:
    """Clear our status and drop the link; returns the token to :func:`hand_back`.

    For a member who disconnects (``keep_to_retry=False``: drop it anyway)
    or leaves the org (``True``: if Slack couldn't be reached, keep the link
    so the next pass clears the status instead of leaving "On leave" up).
    The token is read first: clearing may already have dropped a dead one.
    The caller commits, then hands the token back, so a failed commit
    never leaves a row whose token is already revoked.
    """
    token = decrypt_secret(link.token)
    if not await clear(db, link) and keep_to_retry:
        return None
    await SlackStatusLinkRepository(db, org_id=link.org_id).remove(link.user_id)
    return token or None


async def hand_back(tokens: Iterable[str]) -> None:
    """Revoke tokens we no longer keep (after the commit that dropped them).

    Already revoked, or Slack is down: we've forgotten them, which is what matters.
    """
    for token in tokens:
        with contextlib.suppress(SlackUserApiError, httpx.HTTPError):
            await revoke(token)


async def _wanted(
    db: AsyncSession, link: SlackStatusLink, policy: LeavePolicy, day: date
) -> SlackStatus:
    requests = await LeaveRequestRepository(db, org_id=link.org_id).active_between(
        [link.user_id], day, day
    )
    bookings = [
        Booking(kind=r.kind, start=r.start_date, end=r.end_date, half_day=r.half_day)
        for r in requests
        if r.status == LeaveStatus.APPROVED
    ]
    midday = time.fromisoformat((await load_options(db, link.org_id)).midday)
    return status_for(bookings, day, policy.timezone, midday, datetime.now(UTC))


async def _put(
    db: AsyncSession, link: SlackStatusLink, wanted: SlackStatus, next_at: datetime | None
) -> bool:
    """Make Slack show ``wanted``; False when it's worth retrying soon."""
    links = SlackStatusLinkRepository(db, org_id=link.org_id)
    ids = {"org_id": str(link.org_id), "user_id": str(link.user_id)}
    try:
        token = decrypt_secret(link.token)
        current = await get_status(token)
        if change_needed(current, wanted):
            await set_status(token, wanted)
    except SlackUserApiError as exc:
        if exc.code in DEAD_TOKEN:
            logger.info("slack_status_token_dead", error=exc.code, **ids)
            await links.remove(link.user_id)
            return True
        logger.warning("slack_status_failed", error=exc.code, **ids)
        if exc.code in _RETRY_SOON:
            return False
    except httpx.HTTPError as exc:
        logger.warning("slack_status_unreachable", error=str(exc), **ids)
        return False
    if next_at is not None:
        await links.mark_refreshed(link.user_id, next_at)
    return True
