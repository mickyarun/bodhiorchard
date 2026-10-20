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

"""Leave reports and history over real HTTP: who sees what, and the numbers."""

from __future__ import annotations

import csv
import io
import uuid
from datetime import date
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.leave_request import LeaveKind, LeaveStatus
from tests.integration.leave_support import (
    Factory,
    add_member_without_profile,
    add_request,
    as_user,
    setup_org,
    team,
)

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"
JUNE = {"start": "2026-06-01", "end": "2026-06-30"}


async def test_report_access_follows_leave_reports_and_direct_reports(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, _ = await team(pg_session_factory)
    other_org, (stranger,), _ = await setup_org(pg_session_factory, "Stranger")

    async def scope(user: uuid.UUID, in_org: uuid.UUID = org) -> tuple[int, list[str]]:
        r = await client.get(f"{LEAVE}/reports/scope", headers=as_user(user, in_org))
        names = sorted(x["name"] for x in r.json()["people"]) if r.status_code == 200 else []
        return r.status_code, names

    assert (await scope(p["hr"]))[1] == ["Boss", "Emp", "Hr", "Mgr", "Peer"]
    assert await scope(p["mgr"]) == (200, ["Emp"])
    # Skip-level: the boss sees Mgr, not Mgr's report.
    assert await scope(p["boss"]) == (200, ["Mgr"])
    assert (await scope(p["peer"]))[0] == 403
    # Another org's member reports on their own org only.
    assert await scope(stranger, other_org) == (403, [])
    # A filter for someone outside the scope returns nothing, never their data.
    r = await client.get(
        f"{LEAVE}/reports/summary",
        params={**JUNE, "user_id": str(p["peer"])},
        headers=as_user(p["mgr"], org),
    )
    assert r.status_code == 200 and r.json()["rows"] == []


async def test_summary_splits_leave_at_the_range_and_puts_loss_of_pay_last(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    # Thu 28 May - Wed 3 Jun: 2 days in May, 3 in June; 2 unpaid days at the end.
    await add_request(
        pg_session_factory, org, p["emp"], date(2026, 5, 28), date(2026, 6, 3), "5",
        type_id=casual, lop="2",
    )  # fmt: skip
    await add_request(
        pg_session_factory, org, p["emp"], date(2026, 6, 10), date(2026, 6, 10), "1",
        kind=LeaveKind.WFH,
    )  # fmt: skip
    await add_request(
        pg_session_factory, org, p["emp"], date(2026, 6, 15), date(2026, 6, 15), "1",
        type_id=casual, status=LeaveStatus.PENDING,
    )  # fmt: skip
    hr = as_user(p["hr"], org)
    june = (await client.get(f"{LEAVE}/reports/summary", params=JUNE, headers=hr)).json()
    emp = next(r for r in june["rows"] if r["name"] == "Emp")
    assert Decimal(emp["leave_days"]) == 3 and Decimal(emp["lop_days"]) == 2
    assert Decimal(emp["leave_by_type"][str(casual)]) == 3
    assert (Decimal(emp["wfh_days"]), Decimal(emp["pending_days"])) == (1, 1)
    may = {"start": "2026-05-01", "end": "2026-05-31"}
    emp_may = next(
        r
        for r in (await client.get(f"{LEAVE}/reports/summary", params=may, headers=hr)).json()[
            "rows"
        ]
        if r["name"] == "Emp"
    )
    assert (Decimal(emp_may["leave_days"]), Decimal(emp_may["lop_days"])) == (2, 0)


async def test_members_without_a_profile_still_appear_when_they_took_leave(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    loner = await add_member_without_profile(pg_session_factory, org, "No Profile")
    await add_request(
        pg_session_factory, org, loner, date(2026, 6, 2), date(2026, 6, 2), "1", type_id=casual
    )
    r = await client.get(f"{LEAVE}/reports/summary", params=JUNE, headers=as_user(p["hr"], org))
    assert "No Profile" in [row["name"] for row in r.json()["rows"]]


async def test_register_and_csv_exports(client: AsyncClient, pg_session_factory: Factory) -> None:
    org, p, casual = await team(pg_session_factory)
    await add_request(
        pg_session_factory, org, p["emp"], date(2026, 6, 2), date(2026, 6, 2), "1", type_id=casual
    )
    await add_request(
        pg_session_factory, org, p["peer"], date(2026, 6, 3), date(2026, 6, 3), "1",
        kind=LeaveKind.WFH,
    )  # fmt: skip
    hr = as_user(p["hr"], org)
    every = (await client.get(f"{LEAVE}/reports/register", params=JUNE, headers=hr)).json()
    assert [r["name"] for r in every["rows"]] == ["Emp", "Peer"] and not every["truncated"]
    assert "reason" not in every["rows"][0]
    wfh = await client.get(f"{LEAVE}/reports/register", params={**JUNE, "kind": "wfh"}, headers=hr)
    assert [r["name"] for r in wfh.json()["rows"]] == ["Peer"]
    mine = await client.get(
        f"{LEAVE}/reports/register", params=JUNE, headers=as_user(p["mgr"], org)
    )
    assert [r["name"] for r in mine.json()["rows"]] == ["Emp"]

    for path in ("summary.csv", "register.csv"):
        out = await client.get(f"{LEAVE}/reports/{path}", params=JUNE, headers=hr)
        assert out.status_code == 200
        assert out.headers["content-type"].startswith("text/csv")
        assert out.headers["cache-control"] == "no-store, private"
        assert out.headers["content-disposition"].startswith("attachment;")
        assert out.content.startswith("\ufeff".encode())
    balances = await client.get(f"{LEAVE}/reports/balances.csv", headers=hr)
    rows = list(csv.reader(io.StringIO(balances.content.decode("utf-8-sig"))))
    assert rows[0][:2] == ["Employee", "Code"] and len(rows) == 6  # header + 5 members x 1 type
    bad = await client.get(
        f"{LEAVE}/reports/summary", params={"start": "2026-06-30", "end": "2026-06-01"}, headers=hr
    )
    assert bad.status_code == 422


async def test_balances_report_matches_the_member_balances(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    year = date.today().year
    await add_request(
        pg_session_factory, org, p["emp"], date(year, 1, 6), date(year, 1, 7), "2", type_id=casual
    )
    hr = as_user(p["hr"], org)
    report = (
        await client.get(
            f"{LEAVE}/reports/balances", params={"user_id": str(p["emp"])}, headers=hr
        )
    ).json()["rows"]
    member = (await client.get(f"{LEAVE}/balances/{p['emp']}", headers=hr)).json()["balances"]
    assert len(report) == 1 and len(member) == 1
    for key in ("allocated", "used", "pending", "available"):
        assert Decimal(report[0][key]) == Decimal(member[0][key]), key


async def test_history_is_for_self_managers_and_hr(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    other_org, (stranger,), _ = await setup_org(pg_session_factory, "Stranger")
    year = date.today().year
    await add_request(
        pg_session_factory, org, p["emp"], date(year, 2, 3), date(year, 2, 3), "1", type_id=casual
    )
    path = f"{LEAVE}/history/{p['emp']}"
    for user in ("emp", "mgr", "hr"):
        r = await client.get(path, headers=as_user(p[user], org))
        assert r.status_code == 200 and len(r.json()["rows"]) == 1, user
    for user in ("boss", "peer"):
        assert (await client.get(path, headers=as_user(p[user], org))).status_code == 403
    assert (await client.get(path, headers=as_user(stranger, other_org))).status_code == 404
    out = await client.get(f"{path}/export", headers=as_user(p["emp"], org))
    assert out.status_code == 200 and "Emp" not in out.headers["content-disposition"]
