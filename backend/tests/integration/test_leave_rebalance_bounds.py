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

"""Days left stay at zero or above as HR moves a balance across zero, over HTTP.

Booked leave is re-priced whenever the balance behind it moves: the
earliest leave is paid first and what the balance can't cover is loss
of pay. Upfront 5-day type, today frozen.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.leave_request import LeaveStatus
from app.services.leave.lifecycle import decide, submit
from tests.integration.leave_edge_support import days_left, freeze_today, stored
from tests.integration.leave_support import (
    NOBODY,
    Factory,
    as_user,
    give_role,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
D = Decimal
TODAY = date(2030, 6, 3)  # a Monday
EARLY = (date(2030, 6, 10), date(2030, 6, 11))  # 2 days
LATE = (date(2030, 6, 17), date(2030, 6, 19))  # 3 days


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, TODAY)


async def _setup(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """``(org, emp, mgr, hr, type)``."""
    org, (emp, mgr, hr), casual = await setup_org(factory, "Emp", "Mgr", "Hr")
    await give_role(factory, org, hr, "hr")
    await report_to(factory, org, emp, mgr)
    return org, emp, mgr, hr, casual


async def _book(
    factory: Factory, org: uuid.UUID, emp: uuid.UUID, cl: uuid.UUID, dates: tuple[date, date]
) -> uuid.UUID:
    async with factory() as db:
        request, _ = await submit(db, org, emp, leave_body(cl, *dates))
        await db.commit()
        return request.id


async def _adjust(
    client: AsyncClient, org: uuid.UUID, hr: uuid.UUID, emp: uuid.UUID, cl: uuid.UUID, days: str
) -> Any:
    body = {"leave_type_id": str(cl), "days": days, "note": "Balance fix", "leave_year": 2030}
    return await client.post(
        f"/api/v1/leave/balances/{emp}/adjust", json=body, headers=as_user(hr, org)
    )


async def _lop(factory: Factory, *ids: uuid.UUID) -> list[Decimal]:
    return [(await stored(factory, i)).lop_days for i in ids]


async def test_the_balance_crossing_zero_moves_loss_of_pay_one_day_at_a_time(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, emp, _mgr, hr, cl = await _setup(pg_session_factory)
    early = await _book(pg_session_factory, org, emp, cl, EARLY)
    late = await _book(pg_session_factory, org, emp, cl, LATE)
    # Booked exactly the balance: nothing left, nothing unpaid.
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(0), D(0))
    assert (await _adjust(client, org, hr, emp, cl, "0")).status_code == 422
    # One day taken away: the latest leave loses a day's pay, never the earliest.
    response = await _adjust(client, org, hr, emp, cl, "-1")
    assert response.status_code == 200, response.text
    assert D(response.json()["balances"][0]["available"]) == 0
    assert await _lop(pg_session_factory, early, late) == [D(0), D(1)]
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(0), D(1))
    # Half a day back covers half of it.
    assert (await _adjust(client, org, hr, emp, cl, "0.5")).status_code == 200
    assert await _lop(pg_session_factory, early, late) == [D(0), D("0.5")]
    # Back to exactly the booked days: no loss of pay, still zero left.
    assert (await _adjust(client, org, hr, emp, cl, "0.5")).status_code == 200
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(0), D(0))
    # One more is a spare day, not negative loss of pay.
    assert (await _adjust(client, org, hr, emp, cl, "1")).status_code == 200
    assert await _lop(pg_session_factory, early, late) == [D(0), D(0)]
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(1), D(0))


async def test_taking_away_more_than_the_year_holds_never_goes_negative(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, emp, mgr, hr, cl = await _setup(pg_session_factory)
    early = await _book(pg_session_factory, org, emp, cl, EARLY)
    late = await _book(pg_session_factory, org, emp, cl, LATE)
    async with pg_session_factory() as db:
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=early, approve=True, note=None
        )
        await db.commit()
    response = await _adjust(client, org, hr, emp, cl, "-10")
    assert response.status_code == 200, response.text
    # Approved and pending leave alike become all loss of pay; days left stop at zero.
    assert await _lop(pg_session_factory, early, late) == [D(2), D(3)]
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(0), D(5))
    assert D(response.json()["balances"][0]["available"]) == 0


async def test_rejecting_earlier_leave_pays_later_loss_of_pay(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, emp, mgr, _hr, cl = await _setup(pg_session_factory)
    week = await _book(pg_session_factory, org, emp, cl, (date(2030, 6, 10), date(2030, 6, 14)))
    extra = await _book(pg_session_factory, org, emp, cl, (date(2030, 6, 17), date(2030, 6, 18)))
    assert await _lop(pg_session_factory, week, extra) == [D(0), D(2)]
    async with pg_session_factory() as db:
        await decide(
            db, org_id=org, actor=mgr, perms=NOBODY, request_id=week, approve=False, note="Busy"
        )
        await db.commit()
    rejected = await stored(pg_session_factory, week)
    assert rejected.status == LeaveStatus.REJECTED
    assert await _lop(pg_session_factory, extra) == [D(0)]
    assert await days_left(pg_session_factory, org, emp, 2030) == (D(3), D(0))


async def test_a_grant_to_another_year_leaves_this_years_loss_of_pay_alone(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, emp, _mgr, hr, cl = await _setup(pg_session_factory)
    await _book(pg_session_factory, org, emp, cl, (date(2030, 6, 10), date(2030, 6, 14)))
    extra = await _book(pg_session_factory, org, emp, cl, (date(2030, 6, 17), date(2030, 6, 17)))
    body = {"leave_type_id": str(cl), "days": "3", "note": "Next year", "leave_year": 2031}
    response = await client.post(
        f"/api/v1/leave/balances/{emp}/adjust", json=body, headers=as_user(hr, org)
    )
    assert response.status_code == 200, response.text
    assert await _lop(pg_session_factory, extra) == [D(1)]
    assert await days_left(pg_session_factory, org, emp, 2031) == (D(8), D(0))
