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

"""Public-holiday import (python-holidays) and day recounts after edits.

Imported holidays land as *mandatory*; HR can then rename them, delete
them or mark some optional. Whenever a policy's holidays change, pending
and upcoming requests on it are recounted so their day totals stay right.
"""

import re
import uuid
from datetime import date
from functools import lru_cache

import holidays
import structlog
from holidays import registry
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveKind
from app.models.policy_holiday import HolidayKind, HolidaySource, PolicyHoliday
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.schemas.leave_policy import HolidayCountry, Subdivision
from app.services.leave.calendar_math import count_days, leave_year_bounds, leave_year_by_label
from app.services.leave.errors import LeaveInvalidError
from app.services.leave.loss_of_pay import rebalance, reprice
from app.services.leave.policies import mandatory_holidays, policy_for_request, today_for

logger = structlog.get_logger(__name__)


class HolidayImportError(LeaveInvalidError):
    """The policy has no country set, or python-holidays doesn't know it."""


def _words(class_name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", " ", class_name)


@lru_cache(maxsize=1)
def holiday_countries() -> list[HolidayCountry]:
    """Countries python-holidays covers, with their regions, by name."""
    names = {entry[1]: _words(entry[0]) for entry in registry.COUNTRIES.values()}
    out = []
    for code, subdivision_codes in holidays.list_supported_countries().items():
        aliases = holidays.country_holidays(code).get_subdivision_aliases()
        out.append(
            HolidayCountry(
                code=code,
                name=names.get(code, code),
                subdivisions=[
                    Subdivision(code=sub, name=(aliases.get(sub) or [sub])[0])
                    for sub in subdivision_codes
                ],
            )
        )
    return sorted(out, key=lambda country: country.name)


def public_holidays(country: str, subdivision: str | None, year: int) -> dict[date, str]:
    """``{date: name}`` of a country's (and region's) public holidays."""
    try:
        found = holidays.country_holidays(country, subdiv=subdivision or None, years=year)
    except NotImplementedError as exc:
        raise HolidayImportError(f"Public holidays aren't available for {country}.") from exc
    return dict(sorted(found.items()))


async def import_public_holidays(
    db: AsyncSession, policy: LeavePolicy, leave_year: int
) -> tuple[int, int]:
    """Add one leave year's public holidays; returns ``(added, skipped)``.

    ``leave_year`` is the policy's leave-year label, so a policy whose year
    runs April–March gets April 2026 to March 2027 for "2026" — the same
    range the holidays list shows.
    """
    if not policy.country_code:
        raise HolidayImportError("Set the policy's country before importing holidays.")
    bounds = leave_year_by_label(leave_year, policy.year_start_month)
    found = {
        day: name
        for year in range(bounds.start.year, bounds.end.year + 1)
        for day, name in public_holidays(
            policy.country_code, policy.subdivision_code, year
        ).items()
        if bounds.start <= day <= bounds.end
    }
    if not found:
        return 0, 0
    repo = PolicyHolidayRepository(db, org_id=policy.org_id)
    existing = await repo.existing_dates(policy.id, list(found))
    for day, name in found.items():
        if day not in existing:
            repo.add_staged(
                PolicyHoliday(
                    org_id=policy.org_id,
                    policy_id=policy.id,
                    date=day,
                    name=name[:150],
                    kind=HolidayKind.MANDATORY,
                    source=HolidaySource.IMPORTED,
                )
            )
    await db.flush()
    added = len(found) - len(existing)
    if added:
        await recount_requests(db, policy, min(found))
    return added, len(existing)


async def recount_requests(db: AsyncSession, policy: LeavePolicy, start: date) -> int:
    """Re-price open requests after a holiday or working-day change.

    Takes the affected members' locks so a submit can't check a balance
    against stale day counts meanwhile. Each changed request is split
    into paid and loss-of-pay days again.
    """
    repo = LeaveRequestRepository(db, org_id=policy.org_id)
    # Wait for submits counting against the old calendar to finish, so
    # their requests are found below (LeavePolicyRepository.lock).
    await LeavePolicyRepository(db, org_id=policy.org_id).lock(policy.id, shared=False)
    today = today_for(policy)
    found = await repo.open_for_policy_from(policy.id, start, today)
    if not found:
        return 0
    await repo.lock_members({r.user_id for r in found})
    # Re-read under the locks: a request may have been decided or cancelled.
    requests = [
        r
        for r in await repo.open_for_policy_from(policy.id, start, today)
        if r.kind != LeaveKind.OPTIONAL_HOLIDAY
    ]
    if not requests:
        return 0
    holidays = await mandatory_holidays(
        db, policy, min(r.start_date for r in requests), max(r.end_date for r in requests)
    )
    changed = 0
    for request in requests:
        days = count_days(
            request.start_date,
            request.end_date,
            request.half_day,
            working_days=policy.working_days,
            holidays=holidays,
        ).days
        if days != request.days:
            # Set together: any query below flushes, and loss of pay can't
            # exceed the days (it's given back first).
            request.days, request.lop_days = days, min(request.lop_days, days)
            # Loss of pay follows the new count (and is given back first).
            await reprice(db, await policy_for_request(db, policy.org_id, request), request)
            changed += 1
    # Shorter requests free balance that earlier loss of pay can now use.
    seen: set[tuple[uuid.UUID, uuid.UUID, int]] = set()
    for request in requests:
        member = await policy_for_request(db, policy.org_id, request)
        year = leave_year_bounds(request.start_date, member.policy.year_start_month).label
        key = (request.user_id, request.leave_type_id, year) if request.leave_type_id else None
        if key is None or key in seen:
            continue
        seen.add(key)
        await rebalance(db, member, request.user_id, key[1], request.start_date)
    await db.flush()
    if changed:
        logger.info(
            "leave_requests_recounted",
            policy_id=str(policy.id),
            from_date=start.isoformat(),
            changed=changed,
        )
    return changed
