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

"""The approvals queue over HTTP: who sees whose requests, and by which route."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from httpx import AsyncClient

from app.services.leave.lifecycle import submit
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_role,
    leave_body,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
QUEUE = "/api/v1/leave/approvals"


async def _queue(client: AsyncClient, user: uuid.UUID, org: uuid.UUID) -> list[dict[str, Any]]:
    response = await client.get(QUEUE, headers=as_user(user, org))
    assert response.status_code == 200, response.text
    return list(response.json())


async def test_each_approver_sees_only_what_they_can_decide(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, people, casual = await setup_org(
        pg_session_factory, "Asha", "Bala", "MgrA", "MgrB", "Hr", "Admin", "Peer"
    )
    asha, bala, mgr_a, mgr_b, hr, admin, peer = people
    await report_to(pg_session_factory, org, asha, mgr_a)
    await report_to(pg_session_factory, org, bala, mgr_b)
    await give_role(pg_session_factory, org, hr, "hr")
    await give_role(pg_session_factory, org, admin, "admin")
    mon = future_monday()
    async with pg_session_factory() as db:
        await submit(db, org, asha, leave_body(casual, mon, mon, reason="Dentist"))
        await submit(db, org, bala, leave_body(casual, mon + timedelta(1), mon + timedelta(1)))
        await db.commit()

    seen_a = await _queue(client, mgr_a, org)
    assert [(i["request"]["user"]["name"], i["route"]) for i in seen_a] == [("Asha", "manager")]
    assert seen_a[0]["request"]["reason"] == "Dentist"
    # HR sees everyone, overriding the managers.
    seen_hr = await _queue(client, hr, org)
    assert sorted((i["request"]["user"]["name"], i["route"]) for i in seen_hr) == [
        ("Asha", "hr_override"),
        ("Bala", "hr_override"),
    ]
    # Configuring leave isn't approving it; a peer approves nobody.
    assert await _queue(client, admin, org) == []
    assert await _queue(client, peer, org) == []
    for user, expected in ((mgr_a, 1), (hr, 2), (admin, 0)):
        count = await client.get(f"{QUEUE}/count", headers=as_user(user, org))
        assert count.json()["pending"] == expected


async def test_hr_can_decide_even_when_a_manager_is_set(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, mgr, hr), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Hr")
    await report_to(pg_session_factory, org, emp, mgr)
    await give_role(pg_session_factory, org, hr, "hr")
    mon = future_monday()
    async with pg_session_factory() as db:
        request, _ = await submit(db, org, emp, leave_body(casual, mon, mon))
        await db.commit()
    approved = await client.post(
        f"/api/v1/leave/requests/{request.id}/approve",
        json={"note": None},
        headers=as_user(hr, org),
    )
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "approved"
