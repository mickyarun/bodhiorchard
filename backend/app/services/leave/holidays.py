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
from datetime import date
from functools import lru_cache

import holidays
from holidays import registry
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveKind
from app.models.policy_holiday import HolidayKind, HolidaySource, PolicyHoliday
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.schemas.leave_policy import HolidayCountry, Subdivision
from app.services.leave.calendar_math import count_days
from app.services.leave.policies import mandatory_holidays


class HolidayImportError(ValueError):
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
    db: AsyncSession, policy: LeavePolicy, year: int
) -> tuple[int, int]:
    """Add the year's public holidays to a policy; returns ``(added, skipped)``."""
    if not policy.country_code:
        raise HolidayImportError("Set the policy's country before importing holidays.")
    found = public_holidays(policy.country_code, policy.subdivision_code, year)
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
    """Recount days on pending and upcoming requests after a holiday change."""
    requests = await LeaveRequestRepository(db, org_id=policy.org_id).pending_for_policy_from(
        policy.id, start
    )
    changed = 0
    for request in requests:
        if request.kind == LeaveKind.OPTIONAL_HOLIDAY:
            continue
        holidays_in_range = await mandatory_holidays(
            db, policy, request.start_date, request.end_date
        )
        days = count_days(
            request.start_date,
            request.end_date,
            request.half_day,
            working_days=policy.working_days,
            holidays=holidays_in_range,
        ).days
        if days != request.days:
            request.days = days
            changed += 1
    await db.flush()
    return changed
