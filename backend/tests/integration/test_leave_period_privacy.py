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

"""Period leave stays between her and HR, and nobody grants it to themselves."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.notification import Notification
from tests.integration.leave_support import (
    Factory,
    as_user,
    give_role,
    month_mondays,
    report_to,
    setup_org,
)
from tests.integration.period_support import add_period_leave

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"
PERIOD = "Period leave"


async def _booked(
    client: AsyncClient, factory: Factory
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """Asha (female) took a period day; Mgr is her manager, Hr has the HR role."""
    org, (woman, mgr, hr), _ = await setup_org(factory, "Asha", "Mgr", "Hr")
    await report_to(factory, org, woman, mgr)
    await give_role(factory, org, hr, "hr")
    period = await add_period_leave(factory, org, woman)
    mon = month_mondays()[0]
    sent = await client.post(
        f"{LEAVE}/requests",
        json={"kind": "leave", "leave_type_id": str(period), "start_date": mon.isoformat(),
              "end_date": mon.isoformat()},
        headers=as_user(woman, org),
    )  # fmt: skip
    assert sent.status_code == 201 and sent.json()["status"] == "approved", sent.text
    return org, woman, mgr, hr, period


async def test_the_manager_hears_plain_leave_and_hr_hears_nothing(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, _woman, mgr, hr, _ = await _booked(client, pg_session_factory)
    async with pg_session_factory() as db:
        rows = (await db.scalars(select(Notification).where(Notification.org_id == org))).all()
    to_mgr = [n for n in rows if n.user_id == mgr]
    assert len(to_mgr) == 1 and to_mgr[0].title == "On leave"
    assert "period" not in (to_mgr[0].message or "").lower()
    assert "automatically" not in (to_mgr[0].message or "")
    assert not [n for n in rows if n.user_id == hr]


async def test_managers_see_plain_leave_everywhere_hr_and_she_see_the_type(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, woman, mgr, hr, period = await _booked(client, pg_session_factory)
    mon = month_mondays()[0]
    span = {"start": mon.isoformat(), "end": (mon + timedelta(days=6)).isoformat()}

    async def calendar_type(viewer: uuid.UUID) -> object:
        r = await client.get(f"{LEAVE}/calendar", params=span, headers=as_user(viewer, org))
        [entry] = [e for e in r.json()["entries"] if e["user"]["user_id"] == str(woman)]
        return entry["leave_type"]

    async def balance_names(viewer: uuid.UUID) -> set[str]:
        r = await client.get(f"{LEAVE}/balances/{woman}", headers=as_user(viewer, org))
        assert r.status_code == 200, r.text
        return {b["leave_type"]["name"] for b in r.json()["balances"]}

    assert await calendar_type(mgr) is None
    assert (await calendar_type(hr))["name"] == PERIOD  # type: ignore[index]
    assert PERIOD not in await balance_names(mgr)
    assert PERIOD in await balance_names(hr)
    assert PERIOD in await balance_names(woman)

    history = await client.get(f"{LEAVE}/history/{woman}", headers=as_user(mgr, org))
    assert [row["leave_type"] for row in history.json()["rows"]] == [None]
    summary = await client.get(f"{LEAVE}/reports/summary", params=span, headers=as_user(mgr, org))
    assert PERIOD not in {t["name"] for t in summary.json()["leave_types"]}
    # Left out of the totals too, or total minus the columns would give it away.
    [hers] = [r for r in summary.json()["rows"] if r["user_id"] == str(woman)]
    assert float(hers["leave_days"]) == 0
    hr_summary = await client.get(
        f"{LEAVE}/reports/summary", params=span, headers=as_user(hr, org)
    )
    assert PERIOD in {t["name"] for t in hr_summary.json()["leave_types"]}
    # Filtering the register by the type would list who took it: nothing comes back.
    register = await client.get(
        f"{LEAVE}/reports/register",
        params={**span, "leave_type_id": str(period)},
        headers=as_user(mgr, org),
    )
    assert register.status_code == 200 and register.json()["rows"] == []
    options = await client.get(f"{LEAVE}/reports/scope", headers=as_user(mgr, org))
    assert PERIOD not in {t["name"] for t in options.json()["leave_types"]}


async def test_only_approvers_make_a_type_approve_itself(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (admin, hr), _ = await setup_org(pg_session_factory, "Admin", "Hr")
    await give_role(pg_session_factory, org, admin, "admin")
    await give_role(pg_session_factory, org, hr, "hr")
    policy = (await client.get(f"{LEAVE}/policies", headers=as_user(hr, org))).json()[0]
    url = f"{LEAVE}/policies/{policy['id']}/types"
    body = {"name": "Self", "code": "SELF", "annual_quota_days": "12", "auto_approve": True}
    assert (await client.post(url, json=body, headers=as_user(admin, org))).status_code == 403
    unlimited = {**body, "annual_quota_days": None}
    assert (await client.post(url, json=unlimited, headers=as_user(hr, org))).status_code == 422
    odd = {**body, "monthly_limit_days": "0.7"}
    assert (await client.post(url, json=odd, headers=as_user(hr, org))).status_code == 422
    assert (await client.post(url, json=body, headers=as_user(hr, org))).status_code == 201


async def test_nobody_but_the_owner_changes_their_own_gender(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr, other_hr), _ = await setup_org(pg_session_factory, "Hr", "Hr2")
    for who in (hr, other_hr):
        await give_role(pg_session_factory, org, who, "hr")
    body = {"gender": "female"}
    own = await client.put(f"/api/v1/employees/{hr}/personal", json=body, headers=as_user(hr, org))
    assert own.status_code == 403, own.text
    theirs = await client.put(
        f"/api/v1/employees/{hr}/personal", json=body, headers=as_user(other_hr, org)
    )
    assert theirs.status_code == 200, theirs.text


async def test_balance_tools_act_as_if_the_hidden_type_were_not_there(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, woman, mgr, _hr, period = await _booked(client, pg_session_factory)
    # An admin manager configures leave but doesn't see personal details.
    await give_role(pg_session_factory, org, mgr, "admin")
    headers = as_user(mgr, org)
    body = {"leave_type_id": str(period)}
    recalc = await client.post(f"{LEAVE}/balances/{woman}/recalculate", json=body, headers=headers)
    adjust = await client.post(
        f"{LEAVE}/balances/{woman}/adjust",
        json={**body, "days": "1", "note": "probe"},
        headers=headers,
    )
    for response in (recalc, adjust):
        assert response.status_code != 200
        assert "isn't on this person's policy" in response.text
