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

"""Which leave policy a member follows, and the org's default policy."""

import uuid
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.leave_policy import LeavePolicy
from app.models.policy_holiday import HolidayKind
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.policy_holiday import PolicyHolidayRepository
from app.services.org_settings import get_presence_settings
from app.services.quiz_schedule_math import resolve_zone

_WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
DEFAULT_POLICY_NAME = "Default"


@dataclass(frozen=True)
class MemberPolicy:
    """A member's policy, and their profile if HR has created one."""

    policy: LeavePolicy
    profile: EmployeeProfile | None


async def ensure_default_policy(db: AsyncSession, org_id: uuid.UUID) -> LeavePolicy:
    """The org's default policy, created on first use from presence settings.

    It starts with no leave types, so the Leave page prompts HR to set it up.
    """
    repo = LeavePolicyRepository(db, org_id=org_id)
    existing = await repo.get_default()
    if existing is not None:
        return existing
    org = await OrganizationRepository(db).get_by_id(org_id)
    presence = get_presence_settings(org.config if org else None)
    return await repo.create(
        LeavePolicy(
            org_id=org_id,
            name=DEFAULT_POLICY_NAME,
            timezone=presence.timezone or "UTC",
            working_days=[_WEEKDAY_KEYS.index(key) for key in presence.working_days],
            is_default=True,
        )
    )


async def resolve_member_policy(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID
) -> MemberPolicy:
    """The policy ``user_id`` follows: theirs, else the org default."""
    profile = await EmployeeProfileRepository(db, org_id=org_id).get_by_user(user_id)
    if profile is not None and profile.leave_policy_id is not None:
        policy = await LeavePolicyRepository(db, org_id=org_id).get_by_id(profile.leave_policy_id)
        if policy is not None:
            return MemberPolicy(policy=policy, profile=profile)
    return MemberPolicy(policy=await ensure_default_policy(db, org_id), profile=profile)


def today_for(policy: LeavePolicy) -> date:
    """Today's date in the policy's timezone (the server runs in UTC)."""
    return datetime.now(resolve_zone(policy.timezone)).date()


async def mandatory_holidays(
    db: AsyncSession, policy: LeavePolicy, start: date, end: date
) -> dict[date, str]:
    """``{date: name}`` of the policy's mandatory holidays in a range."""
    rows = await PolicyHolidayRepository(db, org_id=policy.org_id).list_between(
        policy.id, start, end, kind=HolidayKind.MANDATORY
    )
    return {row.date: row.name for row in rows}


def effective_from(profile: EmployeeProfile | None) -> date | None:
    """When the member started counting on their current policy."""
    if profile is None:
        return None
    dates = [d for d in (profile.date_of_joining, profile.leave_policy_assigned_on) if d]
    return max(dates) if dates else None
