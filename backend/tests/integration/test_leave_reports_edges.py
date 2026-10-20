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

"""Leave report edge cases: people without profiles, scope limits, caps, privacy."""

from __future__ import annotations

from datetime import date

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models.employee_profile import EmployeeProfile
from app.models.leave_ledger import LeaveLedgerEntry
from app.models.leave_request import LeaveRequest
from app.models.user import OrgToUser
from app.services.leave.policies import ensure_default_policy
from app.services.leave.reports import register as register_module
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


async def rows(
    client: AsyncClient, path: str, headers: dict[str, str], **params: str
) -> list[dict[str, str]]:
    r = await client.get(f"{LEAVE}/reports/{path}", params=params, headers=headers)
    assert r.status_code == 200, r.text
    return list(r.json()["rows"])


async def test_members_without_a_profile_count_under_the_default_policy(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, _ = await team(pg_session_factory)
    loner = await add_member_without_profile(pg_session_factory, org, "Loner")
    async with pg_session_factory() as db:
        default = (await ensure_default_policy(db, org)).id
    hr = as_user(p["hr"], org)
    summary = await rows(client, "summary", hr, **JUNE, policy_id=str(default))
    assert "Loner" in [r["name"] for r in summary]
    balances = await rows(client, "balances", hr)
    assert "Loner" in [r["name"] for r in balances]
    scope = (await client.get(f"{LEAVE}/reports/scope", headers=hr)).json()
    assert str(loner) in [x["user_id"] for x in scope["people"]]
    # A department filter can't match someone without a profile.
    assert await rows(client, "summary", hr, **JUNE, department="Sales") == []


async def test_a_manager_filter_never_reaches_past_the_viewers_reports(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    await add_request(
        pg_session_factory, org, p["mgr"], date(2026, 6, 2), date(2026, 6, 2), "1", type_id=casual
    )
    mgr = as_user(p["mgr"], org)
    # Mgr asks for the boss's team (which is Mgr): Mgr isn't Mgr's own report.
    assert await rows(client, "register", mgr, **JUNE, manager_id=str(p["boss"])) == []
    assert [r["name"] for r in await rows(client, "summary", mgr, **JUNE)] == ["Emp"]


async def test_caps_return_truncated_json_and_refuse_the_csv(
    client: AsyncClient, pg_session_factory: Factory, monkeypatch: pytest.MonkeyPatch
) -> None:
    org, p, casual = await team(pg_session_factory)
    for day in (2, 3):
        await add_request(
            pg_session_factory, org, p["emp"], date(2026, 6, day), date(2026, 6, day), "1",
            type_id=casual,
        )  # fmt: skip
    monkeypatch.setattr(register_module, "REGISTER_CAP", 1)
    hr = as_user(p["hr"], org)
    r = await client.get(f"{LEAVE}/reports/register", params=JUNE, headers=hr)
    assert r.json()["truncated"] is True and len(r.json()["rows"]) == 1
    out = await client.get(f"{LEAVE}/reports/register.csv", params=JUNE, headers=hr)
    assert out.status_code == 422


async def test_every_export_is_private_and_carries_no_reasons(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, casual = await team(pg_session_factory)
    year = date.today().year
    await add_request(
        pg_session_factory, org, p["emp"], date(year, 6, 2), date(year, 6, 2), "1", type_id=casual
    )
    async with pg_session_factory() as db:
        request = await db.scalar(select(LeaveRequest).where(LeaveRequest.user_id == p["emp"]))
        assert request is not None
        request.reason, request.decision_note = "SECRET-REASON", "SECRET-NOTE"
        await db.commit()
    hr = as_user(p["hr"], org)
    span = {"start": f"{year}-06-01", "end": f"{year}-06-30"}
    urls = [
        (f"{LEAVE}/reports/summary.csv", span),
        (f"{LEAVE}/reports/register.csv", span),
        (f"{LEAVE}/reports/balances.csv", {}),
        (f"{LEAVE}/history/{p['emp']}/export", {}),
    ]
    for url, params in urls:
        out = await client.get(url, params=params, headers=hr)
        assert out.status_code == 200, url
        assert out.headers["cache-control"] == "no-store, private", url
        assert out.headers["content-disposition"].isascii(), url
        assert b"SECRET" not in out.content, url
    for path, params in (("summary", span), ("register", span), ("balances", {})):
        body = (await client.get(f"{LEAVE}/reports/{path}", params=params, headers=hr)).text
        assert "SECRET" not in body, path
    history = (await client.get(f"{LEAVE}/history/{p['emp']}", headers=hr)).text
    assert "SECRET" not in history


async def test_the_balances_report_never_freezes_an_allocation(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, _ = await team(pg_session_factory)

    async def ledger_rows() -> int:
        async with pg_session_factory() as db:
            stmt = (
                select(func.count())
                .select_from(LeaveLedgerEntry)
                .where(LeaveLedgerEntry.org_id == org)
            )
            return int(await db.scalar(stmt) or 0)

    before = await ledger_rows()
    assert await rows(client, "balances", as_user(p["hr"], org))
    assert await ledger_rows() == before


async def test_another_orgs_profile_never_shows(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, p, _ = await team(pg_session_factory)
    other, _, _ = await setup_org(pg_session_factory, "Elsewhere")
    async with pg_session_factory() as db:
        db.add(OrgToUser(user_id=p["emp"], org_id=other))
        db.add(EmployeeProfile(org_id=other, user_id=p["emp"], department="Other Org Dept"))
        here = await db.scalar(
            select(EmployeeProfile).where(
                EmployeeProfile.org_id == org, EmployeeProfile.user_id == p["emp"]
            )
        )
        assert here is not None
        here.department = "Engineering"
        await db.commit()
    hr = as_user(p["hr"], org)
    emp = next(r for r in await rows(client, "summary", hr, **JUNE) if r["name"] == "Emp")
    assert emp["department"] == "Engineering"
