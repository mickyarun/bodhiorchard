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

"""Balances shown outside the Leave page: the summary's "left", approval cards,
and who a policy filter lets in."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.employee_profile import EmployeeProfile
from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveStatus
from app.models.leave_type import LeaveType
from app.services.leave.policies import ensure_default_policy, today_for
from tests.integration.leave_support import (
    Factory,
    add_request,
    as_user,
    give_role,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"
YEAR = date.today().year
WHOLE_YEAR = {"start": f"{YEAR}-01-01", "end": f"{YEAR}-12-31"}


async def _team(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    """HR, a manager and their report with 5 casual days: 2 taken, 1 pending."""
    org, (hr, mgr, emp), casual = await setup_org(factory, "Hr", "Mgr", "Emp")
    await give_role(factory, org, hr, "hr")
    await report_to(factory, org, emp, mgr)
    await add_request(factory, org, emp, date(YEAR, 1, 1), date(YEAR, 1, 1), "1", type_id=casual)
    today = await _policy_today(factory, org)
    await add_request(factory, org, emp, today, today, "1", type_id=casual)
    await add_request(
        factory, org, emp, date(YEAR, 12, 31), date(YEAR, 12, 31), "1",
        type_id=casual, status=LeaveStatus.PENDING,
    )  # fmt: skip
    return org, hr, mgr, emp, casual


async def _policy_today(factory: Factory, org: uuid.UUID) -> date:
    """Today as the server sees it for this org's members (the policy's zone)."""
    async with factory() as db:
        return today_for(await ensure_default_policy(db, org))


async def _get(client: AsyncClient, path: str, headers: dict[str, str], **params: str) -> Any:
    r = await client.get(f"{LEAVE}/{path}", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


async def test_summary_left_matches_the_balances_report(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, hr_id, _mgr, emp, casual = await _team(pg_session_factory)
    hr = as_user(hr_id, org)
    summary = await _get(client, "reports/summary", hr, **WHOLE_YEAR)
    row = next(r for r in summary["rows"] if r["user_id"] == str(emp))
    [column] = summary["leave_types"]
    assert column["name"] == "Casual"
    assert Decimal(row["leave_by_type"][column["key"]]) == 2
    balances = await _get(client, "reports/balances", hr, user_id=str(emp))
    left = Decimal(row["left_by_type"][column["key"]])
    assert left == Decimal(balances["rows"][0]["available"]) == 2
    r = await client.get(f"{LEAVE}/reports/summary.csv", params=WHOLE_YEAR, headers=hr)
    table = list(csv.reader(io.StringIO(r.content.decode("utf-8-sig"))))
    emp_row = dict(zip(table[0], next(t for t in table if t[0] == "Emp"), strict=True))
    assert Decimal(emp_row["Casual taken"]) == Decimal(emp_row["Casual left"]) == 2


async def test_approval_cards_show_every_balance_and_the_last_leave(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, _hr, mgr, _emp, casual = await _team(pg_session_factory)
    [item] = (await _get(client, "approvals", as_user(mgr, org)))["items"]
    assert item["balance_year"] in {YEAR - 1, YEAR}
    # The pending request is this leave year: the card's figure and tiles agree.
    assert item["balance_after_year"] == item["balance_year"]
    [line] = item["balances"]
    assert line["leave_type"]["id"] == str(casual)
    numbers = [Decimal(line[k]) for k in ("used", "pending", "available")]
    assert numbers == [2, 1, 2]
    last = item["last_leave"]
    today = await _policy_today(pg_session_factory, org)
    assert (last["leave_type"], last["start_date"]) == ("Casual", today.isoformat())
    # Decided requests are history: no balances or last leave.
    decided = (await _get(client, "approvals", as_user(mgr, org), status="decided"))["items"]
    assert all(not d["balances"] and d["last_leave"] is None for d in decided)


async def test_a_policy_filter_keeps_other_policies_leave_out(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, hr_id, _mgr, emp, _casual = await _team(pg_session_factory)
    hr = as_user(hr_id, org)
    async with pg_session_factory() as db:
        default = (await ensure_default_policy(db, org)).id
        uk = LeavePolicy(org_id=org, name="UK", timezone="Europe/London")
        db.add(uk)
        await db.flush()
        db.add(
            LeaveType(
                org_id=org,
                policy_id=uk.id,
                name="casual ",
                code="CL",
                annual_quota_days=Decimal("9"),
            )
        )
        profile = (
            await db.execute(select(EmployeeProfile).where(EmployeeProfile.user_id == emp))
        ).scalar_one()
        profile.leave_policy_id = uk.id
        uk_id = uk.id
        await db.commit()
    # Emp took leave but is on the UK policy now: not a default-policy person.
    on_default = await _get(client, "reports/summary", hr, **WHOLE_YEAR, policy_id=str(default))
    assert str(emp) not in [r["user_id"] for r in on_default["rows"]]
    on_uk = await _get(client, "reports/summary", hr, **WHOLE_YEAR, policy_id=str(uk_id))
    assert [r["user_id"] for r in on_uk["rows"]] == [str(emp)]
    # Each policy's "Casual" shares one column; Emp's cell is their UK type,
    # with the leave they took on the old policy still counted as taken.
    everyone = await _get(client, "reports/summary", hr, **WHOLE_YEAR)
    [column] = everyone["leave_types"]
    by_name = {r["name"]: r for r in everyone["rows"]}
    assert Decimal(by_name["Emp"]["leave_by_type"][column["key"]]) == 2
    assert Decimal(by_name["Emp"]["left_by_type"][column["key"]]) == 9
    assert Decimal(by_name["Mgr"]["left_by_type"][column["key"]]) == 5
