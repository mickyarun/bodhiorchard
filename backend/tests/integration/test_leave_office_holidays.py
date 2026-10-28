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

"""Each office counts days on its own calendar, over HTTP.

Two offices with their own policies: a holiday or a Saturday in one is an
ordinary working day in the other. People are placed in offices the way
HR does it, through the employee record.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.policy_holiday import HolidayKind
from tests.integration.leave_edge_support import add_holiday, add_policy, freeze_today, stored
from tests.integration.leave_support import Factory, as_user, give_role, report_to, setup_org

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"
TODAY = date(2030, 6, 3)  # a Monday
FESTIVAL = date(2030, 6, 12)  # a Wednesday, off in Chennai only
SATURDAY = date(2030, 6, 15)  # worked in London only


@pytest.fixture(autouse=True)
def _frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    freeze_today(monkeypatch, TODAY)


@dataclass(frozen=True)
class Offices:
    """An org with a Chennai and a London office, one person in each."""

    org: uuid.UUID
    hr: uuid.UUID
    chennai: tuple[uuid.UUID, uuid.UUID, uuid.UUID]  # person, policy, leave type
    london: tuple[uuid.UUID, uuid.UUID, uuid.UUID]


async def _place(
    client: AsyncClient, org: uuid.UUID, hr: uuid.UUID, user: uuid.UUID, policy: uuid.UUID
) -> None:
    name = f"Office {uuid.uuid4().hex[:6]}"
    created = await client.post(
        "/api/v1/offices",
        json={"name": name, "leave_policy_id": str(policy)},
        headers=as_user(hr, org),
    )
    assert created.status_code == 201, created.text
    # The answer lists every office in the org.
    office = next(o for o in created.json() if o["name"] == name)
    record = (await client.get(f"/api/v1/employees/{user}", headers=as_user(hr, org))).json()
    work = {**record["work"], "office_id": office["id"]}
    placed = await client.put(
        f"/api/v1/employees/{user}/work", json=work, headers=as_user(hr, org)
    )
    assert placed.status_code == 200, placed.text


async def _offices(client: AsyncClient, factory: Factory) -> Offices:
    org, (hr, ravi, amy), _ = await setup_org(factory, "Hr", "Ravi", "Amy")
    await give_role(factory, org, hr, "hr")
    for person in (ravi, amy):
        await report_to(factory, org, person, hr)
    chennai = await add_policy(factory, org, "Chennai")
    london = await add_policy(factory, org, "London", working_days=[0, 1, 2, 3, 4, 5])
    await add_holiday(factory, org, chennai[0], FESTIVAL, "Local festival")
    await _place(client, org, hr, ravi, chennai[0])
    await _place(client, org, hr, amy, london[0])
    return Offices(org, hr, (ravi, *chennai), (amy, *london))


async def _preview(
    client: AsyncClient, org: uuid.UUID, who: tuple[uuid.UUID, uuid.UUID, uuid.UUID], **body: str
) -> dict[str, Any]:
    payload = {"kind": "leave", "leave_type_id": str(who[2]), **body}
    response = await client.post(
        f"{LEAVE}/requests/preview", json=payload, headers=as_user(who[0], org)
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


def _week(start: date, end: date) -> dict[str, str]:
    return {"start_date": start.isoformat(), "end_date": end.isoformat()}


async def test_a_holiday_in_one_office_is_a_working_day_in_another(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    o = await _offices(client, pg_session_factory)
    week = _week(date(2030, 6, 10), date(2030, 6, 14))
    chennai = await _preview(client, o.org, o.chennai, **week)
    assert Decimal(chennai["days"]) == 4 and chennai["problems"] == []
    assert chennai["excluded"] == [{"date": "2030-06-12", "reason": "Local festival"}]
    london = await _preview(client, o.org, o.london, **week)
    assert (Decimal(london["days"]), london["excluded"]) == (5, [])
    # The festival alone: nothing to take in Chennai, a full day in London.
    day = _week(FESTIVAL, FESTIVAL)
    assert [p["code"] for p in (await _preview(client, o.org, o.chennai, **day))["problems"]] == [
        "no_working_days"
    ]
    assert Decimal((await _preview(client, o.org, o.london, **day))["days"]) == 1
    # Half of a holiday is still nothing; half of a working day is half.
    half = await _preview(client, o.org, o.chennai, **day, half_day="first_half")
    assert [p["code"] for p in half["problems"]] == ["no_working_days"]
    assert Decimal(
        (await _preview(client, o.org, o.london, **day, half_day="first_half"))["days"]
    ) == Decimal("0.5")


async def test_each_office_counts_its_own_working_week(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    o = await _offices(client, pg_session_factory)
    saturday = _week(SATURDAY, SATURDAY)
    chennai = await _preview(client, o.org, o.chennai, **saturday)
    assert [p["code"] for p in chennai["problems"]] == ["no_working_days"]
    assert chennai["excluded"] == [{"date": "2030-06-15", "reason": "Sat"}]
    assert Decimal((await _preview(client, o.org, o.london, **saturday))["days"]) == 1


async def test_an_optional_holiday_counts_as_a_working_day(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    o = await _offices(client, pg_session_factory)
    await add_holiday(
        pg_session_factory,
        o.org,
        o.chennai[1],
        date(2030, 6, 13),
        "Pick one",
        HolidayKind.OPTIONAL,
    )
    week = await _preview(client, o.org, o.chennai, **_week(date(2030, 6, 10), date(2030, 6, 14)))
    # Only the mandatory festival is skipped; the optional day is leave.
    assert Decimal(week["days"]) == 4
    assert [e["date"] for e in week["excluded"]] == ["2030-06-12"]


async def test_the_calendar_shows_each_viewer_their_own_offices_holidays(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    o = await _offices(client, pg_session_factory)
    params = {"start": "2030-06-01", "end": "2030-06-30"}
    for who, expected in ((o.chennai[0], ["2030-06-12"]), (o.london[0], [])):
        response = await client.get(
            f"{LEAVE}/calendar", params=params, headers=as_user(who, o.org)
        )
        assert [h["date"] for h in response.json()["holidays"]] == expected


async def test_a_new_holiday_recounts_only_that_offices_pending_leave(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    o = await _offices(client, pg_session_factory)
    week = {"kind": "leave", **_week(date(2030, 6, 17), date(2030, 6, 21))}
    ids = {}
    for who in (o.chennai, o.london):
        body = {**week, "leave_type_id": str(who[2])}
        sent = await client.post(f"{LEAVE}/requests", json=body, headers=as_user(who[0], o.org))
        assert sent.status_code == 201, sent.text
        ids[who[0]] = uuid.UUID(sent.json()["id"])
    added = await client.post(
        f"{LEAVE}/policies/{o.chennai[1]}/holidays",
        json={"date": "2030-06-19", "name": "Second festival"},
        headers=as_user(o.hr, o.org),
    )
    assert added.status_code == 201, added.text
    assert (await stored(pg_session_factory, ids[o.chennai[0]])).days == 4
    assert (await stored(pg_session_factory, ids[o.london[0]])).days == 5
