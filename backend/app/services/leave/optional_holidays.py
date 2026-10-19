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
"""Optional holidays: what a member may still pick this leave year."""

import uuid
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveKind, LeaveStatus
from app.models.policy_holiday import HolidayKind, PolicyHoliday
from app.repositories.leave_request import LeaveRequestRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.services.leave.calendar_math import leave_year_bounds


@dataclass
class OptionalHolidayUse:
    """Quota, use, and the holidays still available to pick."""

    quota: int
    used: int = 0
    pending: int = 0
    available: list[PolicyHoliday] = field(default_factory=list)
    holiday: PolicyHoliday | None = None

    @property
    def remaining(self) -> int:
        """Optional holidays still free to request."""
        return max(0, self.quota - self.used - self.pending)


async def optional_holiday_use(
    db: AsyncSession, policy: LeavePolicy, user_id: uuid.UUID, on: date
) -> OptionalHolidayUse:
    r"""A member's optional-holiday use for the leave year containing \`\`on\`\`."""
    year = leave_year_bounds(on, policy.year_start_month)
    use = OptionalHolidayUse(quota=policy.optional_holiday_quota)
    taken = await LeaveRequestRepository(db, org_id=policy.org_id).active_between(
        [user_id], year.start, year.end, kinds=[LeaveKind.OPTIONAL_HOLIDAY]
    )
    use.used = sum(1 for r in taken if r.status == LeaveStatus.APPROVED)
    use.pending = sum(1 for r in taken if r.status == LeaveStatus.PENDING)
    taken_ids = {r.holiday_id for r in taken}
    holidays = await PolicyHolidayRepository(db, org_id=policy.org_id).list_between(
        policy.id, year.start, year.end, kind=HolidayKind.OPTIONAL
    )
    use.available = [h for h in holidays if h.id not in taken_ids]
    return use


async def pick_optional_holiday(
    db: AsyncSession, policy: LeavePolicy, user_id: uuid.UUID, holiday_id: uuid.UUID | None
) -> OptionalHolidayUse:
    r"""Look up \`\`holiday_id\`\` as one of the policy's optional holidays.

    \`\`holiday\`\` stays None if it isn't an optional holiday on this policy.
    """
    holiday = None
    if holiday_id is not None:
        holiday = await PolicyHolidayRepository(db, org_id=policy.org_id).get_by_id(holiday_id)
    if holiday is None or holiday.policy_id != policy.id or holiday.kind != HolidayKind.OPTIONAL:
        return OptionalHolidayUse(quota=policy.optional_holiday_quota)
    use = await optional_holiday_use(db, policy, user_id, holiday.date)
    use.holiday = holiday
    return use
