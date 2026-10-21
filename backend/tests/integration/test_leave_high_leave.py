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


"""Unlimited leave warns at the policy's lines, wherever people look."""

from __future__ import annotations

import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.leave_type import LeaveType
from app.services.leave.evaluation import evaluate
from app.services.leave.policies import ensure_default_policy, resolve_member_policy
from app.services.leave.summary import build_summary
from tests.integration.leave_support import (
    Factory,
    add_request,
    as_user,
    future_monday,
    give_role,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
D = Decimal


async def _unlimited_with_lines(factory: Factory, org: uuid.UUID, casual: uuid.UUID) -> uuid.UUID:
    """Casual becomes unlimited, the policy warns at 3 then 5, and sick doesn't count."""
    async with factory() as db:
        policy = await ensure_default_policy(db, org)
        policy.leave_notice_days, policy.leave_warning_days = 3, 5
        (await db.get(LeaveType, casual)).annual_quota_days = None  # type: ignore[union-attr]
        sick = LeaveType(
            org_id=org, policy_id=policy.id, name="Sick", code="SL", counts_toward_warning=False
        )
        db.add(sick)
        await db.commit()
        return sick.id


async def test_heads_up_then_warning_for_the_requester_approver_and_hr(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    await give_role(pg_session_factory, org, hr, "hr")
    sick = await _unlimited_with_lines(pg_session_factory, org, casual)
    year = future_monday().year
    jan = date(year, 1, 5)
    await add_request(
        pg_session_factory, org, emp, jan, jan + timedelta(days=1), "2", type_id=casual
    )
    # Sick leave doesn't count toward the lines.
    await add_request(
        pg_session_factory,
        org,
        emp,
        jan + timedelta(days=7),
        jan + timedelta(days=11),
        "5",
        type_id=sick,
    )

    mon = future_monday()
    async with pg_session_factory() as db:
        member = await resolve_member_policy(db, org, emp)
        # 2 taken + 1 asked = 3: the heads-up.
        one = await evaluate(db, member=member, user_id=emp, body=leave_body(casual, mon, mon))
        assert one.high_leave is not None and one.high_leave.level == "notice"
        assert one.high_leave.taken == D(3)
        # 2 + 3 = 5: the warning. A request on the sick type never warns.
        three = await evaluate(
            db, member=member, user_id=emp, body=leave_body(casual, mon, mon + timedelta(days=2))
        )
        assert three.high_leave is not None and three.high_leave.level == "warning"
        sick_ask = await evaluate(db, member=member, user_id=emp, body=leave_body(sick, mon, mon))
        assert sick_ask.high_leave is None

    # Send 2 more days (now 4 taken, pending included): heads-up everywhere.
    r = await client.post(
        "/api/v1/leave/requests",
        json={"kind": "leave", "leave_type_id": str(casual), "start_date": mon.isoformat(),
              "end_date": (mon + timedelta(days=1)).isoformat()},
        headers=as_user(emp, org),
    )  # fmt: skip
    assert r.status_code == 201, r.text
    async with pg_session_factory() as db:
        summary = await build_summary(db, org, emp, year)
    assert summary.high_leave is not None and summary.high_leave.taken == D(4)
    [card] = (await client.get("/api/v1/leave/approvals", headers=as_user(mgr, org))).json()[
        "items"
    ]
    assert card["high_leave"]["level"] == "notice"
    report = await client.get(
        "/api/v1/leave/reports/summary",
        params={"start": f"{year}-01-01", "end": f"{year}-12-31"},
        headers=as_user(hr, org),
    )
    row = next(x for x in report.json()["rows"] if x["user_id"] == str(emp))
    assert row["high_leave"]["level"] == "notice" and D(row["high_leave"]["taken"]) == 4
    # Someone below the lines has no flag.
    other = next(x for x in report.json()["rows"] if x["user_id"] == str(mgr))
    assert other["high_leave"] is None
