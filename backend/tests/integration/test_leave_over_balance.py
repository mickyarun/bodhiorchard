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

"""A type that stops at its balance refuses more, instead of going unpaid."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.leave_type import LeaveType
from app.services.leave.errors import LeaveConflictError
from app.services.leave.lifecycle import submit
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
D = Decimal


async def test_sick_past_its_balance_is_refused_and_points_at_casual(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, mgr), _casual = await setup_org(pg_session_factory, "Emp", "Mgr")
    await report_to(pg_session_factory, org, emp, mgr)
    async with pg_session_factory() as db:
        policy = await ensure_default_policy(db, org)
        sick = LeaveType(
            org_id=org, policy_id=policy.id, name="Sick", code="SL",
            annual_quota_days=D(2), stops_at_balance=True,
        )  # fmt: skip
        db.add(sick)
        await db.commit()
    mon = future_monday()
    async with pg_session_factory() as db:
        with pytest.raises(
            LeaveConflictError, match="request that much.*Casual \\(5 days left\\)"
        ):
            await submit(db, org, emp, leave_body(sick.id, mon, mon + timedelta(days=2)))
        # Within the balance it goes through as usual, fully paid.
        request, _ = await submit(db, org, emp, leave_body(sick.id, mon, mon + timedelta(days=1)))
        await db.commit()
        assert request.lop_days == D(0)
    later = (mon + timedelta(days=7)).isoformat()
    body = {"kind": "leave", "leave_type_id": str(sick.id), "start_date": later, "end_date": later}
    preview = await client.post(
        "/api/v1/leave/requests/preview", json=body, headers=as_user(emp, org)
    )
    assert [p["code"] for p in preview.json()["problems"]] == ["over_balance"]
    assert preview.json()["problems"][0]["message"].startswith("You have no Sick left.")
