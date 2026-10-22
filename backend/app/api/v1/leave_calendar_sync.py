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

"""Settings for Google Calendar sync, and a check that it can reach a calendar (HR)."""

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_permissions
from app.models.user import User
from app.schemas.leave_calendar_sync import (
    CalendarSyncSettings,
    CalendarSyncTestResult,
    CalendarSyncUpdate,
)
from app.services.background import spawn
from app.services.google import calendar_api
from app.services.google.calendar_api import CalendarApiError
from app.services.google.service_account import GoogleAuthError, access_token
from app.services.leave.calendar_sync.settings import load_settings, load_sync, save_settings
from app.services.leave.calendar_sync.sync import backfill
from app.services.leave.permissions import CONFIGURE

router = APIRouter(tags=["leave-admin"])


@router.get("/calendar-sync", response_model=CalendarSyncSettings)
async def get_calendar_sync(
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> CalendarSyncSettings:
    """The org's calendar sync settings (never the key)."""
    return await load_settings(db, current_user.org_id)


@router.put("/calendar-sync", response_model=CalendarSyncSettings)
async def put_calendar_sync(
    body: CalendarSyncUpdate,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> CalendarSyncSettings:
    """Save; then re-sync upcoming approved leave (added when on, removed when off)."""
    org_id = current_user.org_id
    try:
        saved = await save_settings(db, org_id, body)
    except GoogleAuthError as exc:
        raise HTTPException(
            status_code=422, detail="That isn't a service account JSON key."
        ) from exc
    await db.commit()
    if saved.service_account_email:
        # Idempotent, so re-saving just re-checks every upcoming request.
        spawn(backfill(org_id))
    return saved


@router.post("/calendar-sync/test", response_model=CalendarSyncTestResult)
async def test_calendar_sync(
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> CalendarSyncTestResult:
    """Act as the caller and open their calendar: proves the key and the delegation."""
    sync = await load_sync(db, current_user.org_id)
    if sync.key is None:
        return CalendarSyncTestResult(ok=False, error="no_key")
    try:
        token = await access_token(sync.key, current_user.email, calendar_api.SCOPE)
        calendar = await calendar_api.calendar_name(token)
    except GoogleAuthError as exc:
        return CalendarSyncTestResult(ok=False, error=exc.code)
    except CalendarApiError as exc:
        return CalendarSyncTestResult(ok=False, error=f"calendar_{exc.status}", detail=exc.detail)
    except httpx.HTTPError:
        return CalendarSyncTestResult(ok=False, error="google_unreachable")
    return CalendarSyncTestResult(ok=True, calendar=calendar)
