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

"""Holiday calendars per policy, including public-holiday import."""

import uuid

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._leave_admin import load_policy
from app.core.deps import get_db, require_permissions
from app.models.policy_holiday import HolidayKind, HolidaySource, PolicyHoliday
from app.models.user import User
from app.repositories.leave_usage import LeaveUsageRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.schemas.leave_policy import (
    HolidayAdminRead,
    HolidayCountry,
    HolidayImport,
    HolidayImportResult,
    HolidayWrite,
)
from app.services.leave.calendar_math import leave_year_by_label
from app.services.leave.errors import LeaveConflictError, LeaveNotFoundError
from app.services.leave.holidays import (
    holiday_countries,
    import_public_holidays,
    recount_requests,
)
from app.services.leave.permissions import CONFIGURE

router = APIRouter(tags=["leave-admin"])

DUPLICATE = "There's already a holiday on that date."


def _read(h: PolicyHoliday) -> HolidayAdminRead:
    return HolidayAdminRead(id=h.id, date=h.date, name=h.name, kind=h.kind, source=h.source)


async def _load(db: AsyncSession, org_id: uuid.UUID, holiday_id: uuid.UUID) -> PolicyHoliday:
    holiday = await PolicyHolidayRepository(db, org_id=org_id).get_by_id(holiday_id)
    if holiday is None:
        raise LeaveNotFoundError("Holiday not found.")
    return holiday


@router.get("/holiday-countries", response_model=list[HolidayCountry])
async def list_countries(
    _user: User = Depends(require_permissions(CONFIGURE)),
) -> list[HolidayCountry]:
    """Countries and regions public holidays can be imported for."""
    return holiday_countries()


@router.get("/policies/{policy_id}/holidays", response_model=list[HolidayAdminRead])
async def list_holidays(
    policy_id: uuid.UUID,
    year: int = Query(..., ge=2000, le=2100),
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> list[HolidayAdminRead]:
    """Holidays in one of the policy's leave years."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    bounds = leave_year_by_label(year, policy.year_start_month)
    rows = await PolicyHolidayRepository(db, org_id=current_user.org_id).list_between(
        policy.id, bounds.start, bounds.end
    )
    return [_read(h) for h in rows]


@router.post(
    "/policies/{policy_id}/holidays",
    response_model=HolidayAdminRead,
    status_code=status.HTTP_201_CREATED,
)
async def add_holiday(
    policy_id: uuid.UUID,
    body: HolidayWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> HolidayAdminRead:
    """Add a holiday by hand."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    try:
        holiday = await PolicyHolidayRepository(db, org_id=current_user.org_id).create(
            PolicyHoliday(
                org_id=current_user.org_id,
                policy_id=policy.id,
                source=HolidaySource.MANUAL,
                **body.model_dump(),
            )
        )
    except IntegrityError as exc:
        raise LeaveConflictError(DUPLICATE) from exc
    await recount_requests(db, policy, holiday.date)
    return _read(holiday)


async def _refuse_if_booked(db: AsyncSession, holiday: PolicyHoliday) -> None:
    """409 if people booked this optional holiday: their requests would keep its old date."""
    if holiday.kind != HolidayKind.OPTIONAL:
        return
    if await LeaveUsageRepository(db, org_id=holiday.org_id).holiday_booked(holiday.id):
        raise LeaveConflictError(
            "People have booked this optional holiday, so its date and type can't change "
            "and it can't be deleted. They can cancel their requests first; renaming is fine."
        )


@router.put("/holidays/{holiday_id}", response_model=HolidayAdminRead)
async def update_holiday(
    holiday_id: uuid.UUID,
    body: HolidayWrite,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> HolidayAdminRead:
    """Rename, move, or switch a holiday between mandatory and optional."""
    holiday = await _load(db, current_user.org_id, holiday_id)
    if body.date != holiday.date or body.kind != holiday.kind:
        await _refuse_if_booked(db, holiday)
    earliest = min(holiday.date, body.date)
    for field, value in body.model_dump().items():
        setattr(holiday, field, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        raise LeaveConflictError(DUPLICATE) from exc
    policy = await load_policy(db, current_user.org_id, holiday.policy_id)
    await recount_requests(db, policy, earliest)
    return _read(holiday)


@router.delete("/holidays/{holiday_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_holiday(
    holiday_id: uuid.UUID,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Remove a holiday; requests over that date are recounted."""
    holiday = await _load(db, current_user.org_id, holiday_id)
    await _refuse_if_booked(db, holiday)
    policy = await load_policy(db, current_user.org_id, holiday.policy_id)
    on = holiday.date
    await PolicyHolidayRepository(db, org_id=current_user.org_id).delete(holiday)
    await recount_requests(db, policy, on)


@router.post("/policies/{policy_id}/holidays/import", response_model=HolidayImportResult)
async def import_holidays(
    policy_id: uuid.UUID,
    body: HolidayImport,
    current_user: User = Depends(require_permissions(CONFIGURE)),
    db: AsyncSession = Depends(get_db),
) -> HolidayImportResult:
    """Pre-fill a year's public holidays for the policy's country and region."""
    policy = await load_policy(db, current_user.org_id, policy_id)
    added, skipped = await import_public_holidays(db, policy, body.year)
    return HolidayImportResult(added=added, skipped=skipped)
