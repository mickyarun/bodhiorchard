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

"""Fixed-date helpers for the leave edge-case tests.

:func:`freeze_today` pins every policy's "today", so a test can use real
calendar dates (a Dec 31, a leap day, an April leave year) and keeps
meaning the same thing whatever day the suite runs on.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveRequest
from app.models.leave_type import LeaveAccrual, LeaveType
from app.models.policy_holiday import HolidayKind, PolicyHoliday
from app.models.user import User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.services.leave import policies
from app.services.leave.summary import build_summary
from tests.integration.leave_support import Factory

_REAL_TODAY_FOR = policies.today_for


def freeze_today(monkeypatch: pytest.MonkeyPatch, day: date) -> None:
    """Make every policy's today ``day``, in each module that imported ``today_for``."""
    monkeypatch.setattr(policies, "today_for", lambda _policy: day)
    for name, module in list(sys.modules.items()):
        if name.startswith("app.") and getattr(module, "today_for", None) is _REAL_TODAY_FOR:
            monkeypatch.setattr(module, "today_for", lambda _policy: day)


async def add_policy(
    factory: Factory,
    org: uuid.UUID,
    name: str,
    *,
    quota: str = "5",
    accrual: LeaveAccrual = LeaveAccrual.UPFRONT,
    year_start_month: int = 1,
    working_days: list[int] | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    """A non-default policy with one leave type; returns ``(policy id, type id)``."""
    async with factory() as db:
        policy = LeavePolicy(
            org_id=org,
            name=name,
            timezone="UTC",
            working_days=working_days if working_days is not None else [0, 1, 2, 3, 4],
            year_start_month=year_start_month,
        )
        db.add(policy)
        await db.flush()
        leave_type = LeaveType(
            org_id=org,
            policy_id=policy.id,
            name=f"Casual {name}",
            code="CL",
            annual_quota_days=Decimal(quota),
            accrual=accrual,
        )
        db.add(leave_type)
        await db.commit()
        return policy.id, leave_type.id


async def place(factory: Factory, org: uuid.UUID, user: uuid.UUID, policy_id: uuid.UUID) -> None:
    """Put ``user`` on ``policy_id`` (no transfer date, so no proration)."""
    async with factory() as db:
        profile = await EmployeeProfileRepository(db, org_id=org).get_by_user(user)
        assert profile is not None
        profile.leave_policy_id = policy_id
        await db.commit()


async def add_holiday(
    factory: Factory,
    org: uuid.UUID,
    policy_id: uuid.UUID,
    day: date,
    name: str,
    kind: HolidayKind = HolidayKind.MANDATORY,
) -> uuid.UUID:
    """A holiday on one policy's calendar."""
    async with factory() as db:
        holiday = PolicyHoliday(org_id=org, policy_id=policy_id, date=day, name=name, kind=kind)
        db.add(holiday)
        await db.commit()
        return holiday.id


async def stored(factory: Factory, request_id: uuid.UUID) -> LeaveRequest:
    """A request as it is in the database now."""
    async with factory() as db:
        request = await db.get(LeaveRequest, request_id)
        assert request is not None
        return request


async def days_left(
    factory: Factory, org: uuid.UUID, user: uuid.UUID, year: int | None = None
) -> tuple[Decimal | None, Decimal]:
    """The Leave page's days left on the first type, and the year's loss of pay."""
    async with factory() as db:
        summary = await build_summary(db, org, user, year)
    return summary.balances[0].available, summary.lop_days


async def deactivate(factory: Factory, user: uuid.UUID) -> None:
    """Switch a user's account off."""
    async with factory() as db:
        row = await db.get(User, user)
        assert row is not None
        row.is_active = False
        await db.commit()
