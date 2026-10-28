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

"""A manager moving approved leave across Dec 31, over HTTP (today frozen).

Moved into the next leave year, the leave is priced on that year and the
days it freed pay the old year's loss of pay. A move that would span both
years, land only on a weekend, or come from another org changes nothing.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.leave_request import LeaveStatus
from tests.integration.leave_edge_support import (
    days_left,
    freeze_today,
    quiet_notifications,
    stored,
)
from tests.integration.leave_support import Factory, as_user, give_role, setup_org, team

pytestmark = pytest.mark.integration
D = Decimal
LEAVE = "/api/v1/leave/requests"


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, date(2030, 12, 2))
    quiet_notifications(monkeypatch)


async def _approved(
    client: AsyncClient,
    org: uuid.UUID,
    p: dict[str, uuid.UUID],
    type_id: uuid.UUID,
    start: str,
    end: str,
) -> uuid.UUID:
    body = {"kind": "leave", "leave_type_id": str(type_id), "start_date": start, "end_date": end}
    made = await client.post(LEAVE, json=body, headers=as_user(p["emp"], org))
    assert made.status_code == 201, made.text
    request_id = made.json()["id"]
    ok = await client.post(
        f"{LEAVE}/{request_id}/approve", json={}, headers=as_user(p["mgr"], org)
    )
    assert ok.status_code == 200, ok.text
    return uuid.UUID(request_id)


async def _move(
    client: AsyncClient,
    org: uuid.UUID,
    actor: uuid.UUID,
    request_id: uuid.UUID,
    start: str,
    end: str,
) -> tuple[int, str]:
    """``(status, detail)`` of a reschedule; detail is "" on success."""
    response = await client.post(
        f"{LEAVE}/{request_id}/reschedule",
        json={"start_date": start, "end_date": end, "note": "Moved"},
        headers=as_user(actor, org),
    )
    body = response.json()
    return response.status_code, str(body.get("detail", "")) if response.is_error else ""


async def test_moving_leave_into_next_year_pays_this_years_loss_of_pay(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, cl = await team(pg_session_factory)
    week = await _approved(client, org, p, cl, "2030-12-09", "2030-12-13")
    extra = await _approved(client, org, p, cl, "2030-12-16", "2030-12-16")
    assert (await stored(pg_session_factory, extra)).lop_days == 1
    assert await _move(client, org, p["mgr"], week, "2031-01-06", "2031-01-10") == (200, "")
    moved = await stored(pg_session_factory, week)
    assert (moved.status, moved.start_date, moved.days, moved.lop_days) == (
        LeaveStatus.APPROVED,
        date(2031, 1, 6),
        D(5),
        D(0),
    )
    # The week's 5 days went back to 2030: the extra day is paid now.
    assert (await stored(pg_session_factory, extra)).lop_days == 0
    assert await days_left(pg_session_factory, org, p["emp"], 2030) == (D(4), D(0))
    assert await days_left(pg_session_factory, org, p["emp"], 2031) == (D(0), D(0))


@pytest.mark.parametrize(
    ("start", "end", "status", "detail"),
    [
        (
            "2030-12-30",
            "2031-01-03",
            409,
            "Requests can't span two leave years. Split it at Tue 31 Dec.",
        ),
        ("2031-01-04", "2031-01-05", 409, "These dates are all weekends or holidays."),
        ("2030-11-25", "2030-11-25", 422, "Pick dates from today on."),
    ],
)
async def test_a_move_that_breaks_a_rule_changes_nothing(
    client: AsyncClient,
    pg_session_factory: Factory,
    start: str,
    end: str,
    status: int,
    detail: str,
) -> None:
    org, p, cl = await team(pg_session_factory)
    week = await _approved(client, org, p, cl, "2030-12-09", "2030-12-10")
    assert await _move(client, org, p["mgr"], week, start, end) == (status, detail)
    kept = await stored(pg_session_factory, week)
    assert (kept.status, kept.start_date, kept.end_date, kept.days) == (
        LeaveStatus.APPROVED,
        date(2030, 12, 9),
        date(2030, 12, 10),
        D(2),
    )
    assert await days_left(pg_session_factory, org, p["emp"], 2030) == (D(3), D(0))


async def test_hr_of_another_org_cannot_move_or_withdraw_leave(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, cl = await team(pg_session_factory)
    other, (outsider,), _ = await setup_org(pg_session_factory, "OutsideHr")
    await give_role(pg_session_factory, other, outsider, "hr")
    week = await _approved(client, org, p, cl, "2030-12-09", "2030-12-10")
    assert (await _move(client, other, outsider, week, "2030-12-11", "2030-12-12"))[0] == 404
    withdrawn = await client.post(
        f"{LEAVE}/{week}/withdraw", json={"note": "No"}, headers=as_user(outsider, other)
    )
    assert withdrawn.status_code == 404
    assert (await stored(pg_session_factory, week)).status == LeaveStatus.APPROVED
