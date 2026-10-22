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
"""Make a person's Google Calendar match one request, after it changes.

Runs in the background after the change commits, and reconciles rather
than replays: it reads the request as it is now, works out the events it
should have (none unless approved), and fixes whatever is on the calendar.
So approving, rejecting, cancelling and part-cancelling all take the same
path, and running it twice does no harm.

With sync switched off but a key still saved, it only removes: nothing new
is added, but cancelled leave doesn't keep declining meetings.

Best effort, like Slack: failures are logged, the request is already saved.
"""

import asyncio
import uuid
from datetime import date, timedelta

import httpx
import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.models.leave_request import LeaveRequest, LeaveStatus
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.user import UserRepository
from app.services.google import calendar_api
from app.services.google.calendar_api import CalendarApiError, Event
from app.services.google.service_account import GoogleAuthError, access_token
from app.services.leave.calendar_sync.events import (
    STATUS_TYPES,
    RequestShape,
    plain_event,
    wanted_events,
)
from app.services.leave.calendar_sync.settings import CalendarSync, load_sync
from app.services.leave.policies import mandatory_holidays, policy_for_request

logger = structlog.get_logger(__name__)

# One sync per request at a time, so a quick approve-then-cancel can't
# finish in the wrong order and leave an event behind.
# Counted so the lock is dropped only once nobody holds or awaits it.
_locks: dict[uuid.UUID, tuple[asyncio.Lock, int]] = {}


def _take(request_id: uuid.UUID) -> asyncio.Lock:
    lock, users = _locks.get(request_id, (asyncio.Lock(), 0))
    _locks[request_id] = (lock, users + 1)
    return lock


def _drop(request_id: uuid.UUID) -> None:
    lock, users = _locks[request_id]
    if users <= 1:
        del _locks[request_id]
    else:
        _locks[request_id] = (lock, users - 1)


async def sync_request(org_id: uuid.UUID, request_id: uuid.UUID) -> None:
    """Bring the requester's calendar in line with the request (background)."""
    lock = _take(request_id)
    try:
        async with lock:
            async with AsyncSessionLocal() as db:
                sync = await load_sync(db, org_id)
                if sync.key is None:
                    return
                plan = await _plan(db, org_id, request_id, sync)
            if plan is not None:
                await _apply(sync, *plan)
    except (GoogleAuthError, CalendarApiError, httpx.HTTPError) as exc:
        logger.warning(
            "leave_calendar_sync_failed",
            org_id=str(org_id),
            request_id=str(request_id),
            error=str(exc),
        )
    finally:
        _drop(request_id)


async def _plan(
    db: AsyncSession, org_id: uuid.UUID, request_id: uuid.UUID, sync: CalendarSync
) -> tuple[str, str, dict[str, Event]] | None:
    """(calendar owner's email, request tag, events it should have), or None to skip."""
    request = await LeaveRequestRepository(db, org_id=org_id).get_by_id(request_id)
    if request is None:
        return None
    user = await UserRepository(db).get_by_id_in_org(request.user_id, org_id)
    if user is None or not user.email:
        return None
    shape = await _shape(db, org_id, request)
    wanted = wanted_events(shape, sync.options, approved=request.status == LeaveStatus.APPROVED)
    return user.email, shape.request_hex, wanted


async def _shape(db: AsyncSession, org_id: uuid.UUID, request: LeaveRequest) -> RequestShape:
    policy = (await policy_for_request(db, org_id, request)).policy
    holidays = await mandatory_holidays(db, policy, request.start_date, request.end_date)
    return RequestShape(
        request_hex=request.id.hex,
        kind=request.kind,
        start=request.start_date,
        end=request.end_date,
        half_day=request.half_day,
        timezone=policy.timezone,
        working_days=policy.working_days,
        holidays=holidays,
    )


async def _apply(sync: CalendarSync, email: str, tag: str, wanted: dict[str, Event]) -> None:
    assert sync.key is not None  # checked by ``sync_request``
    token = await access_token(sync.key, email, calendar_api.SCOPE)
    existing = await calendar_api.tagged_event_ids(token, tag)
    for event_id, body in wanted.items():
        await _put(token, event_id, body, exists=event_id in existing)
    for event_id in existing - wanted.keys():
        await calendar_api.delete_event(token, event_id)


async def _put(token: str, event_id: str, body: Event, *, exists: bool) -> None:
    """Write the event; if the edition refuses its status type, write a plain one.

    An event keeps the type it was first made with, so once a plain one
    exists it's updated as plain.
    """
    if body.get("eventType") not in STATUS_TYPES:
        await calendar_api.put_event(token, event_id, body, exists=exists)
        return
    try:
        await calendar_api.put_event(token, event_id, body, exists=exists)
    except CalendarApiError as exc:
        if exc.status not in (400, 403):
            raise
        logger.info("leave_calendar_status_event_refused", status=exc.status, detail=exc.detail)
        await calendar_api.put_event(token, event_id, plain_event(body), exists=exists)


async def backfill(org_id: uuid.UUID) -> None:
    """Re-sync every approved request that hasn't ended (after the settings are saved).

    Switched on, that adds them; switched off, it takes them off again.
    One request failing doesn't stop the rest.
    """
    async with AsyncSessionLocal() as db:
        if (await load_sync(db, org_id)).key is None:
            return
        ids = await _upcoming_approved(db, org_id)
    logger.info("leave_calendar_backfill", org_id=str(org_id), requests=len(ids))
    for request_id in ids:
        try:
            await sync_request(org_id, request_id)
        except Exception:
            logger.exception(
                "leave_calendar_backfill_failed", org_id=str(org_id), request_id=str(request_id)
            )


async def _upcoming_approved(db: AsyncSession, org_id: uuid.UUID) -> list[uuid.UUID]:
    # Policies' "today" can be a day either side of UTC's; a day early is harmless.
    first_day = date.today() - timedelta(days=1)
    requests = await LeaveRequestRepository(db, org_id=org_id).active_between(
        None, first_day, date.max
    )
    return [r.id for r in requests if r.status == LeaveStatus.APPROVED]
