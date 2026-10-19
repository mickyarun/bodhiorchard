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

"""Who may do what on the leave API, over real HTTP and real roles.

Each test signs in with real access tokens; permissions come from the
seeded system roles (hr, admin, org_owner) or none at all.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.services.leave.policies import resolve_member_policy
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_role,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"


async def _request(
    client: AsyncClient, org: uuid.UUID, user: uuid.UUID, type_id: uuid.UUID
) -> str:
    day = future_monday().isoformat()
    body = {"kind": "leave", "leave_type_id": str(type_id), "start_date": day, "end_date": day}
    response = await client.post(f"{LEAVE}/requests", json=body, headers=as_user(user, org))
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_only_managers_decide_and_only_the_requester_cancels(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, mgr, peer), casual = await setup_org(pg_session_factory, "Emp", "Mgr", "Peer")
    other_org, (stranger,), _ = await setup_org(pg_session_factory, "Stranger")
    await report_to(pg_session_factory, org, emp, mgr)
    request_id = await _request(client, org, emp, casual)

    approve = f"{LEAVE}/requests/{request_id}/approve"
    assert (await client.post(approve, json={}, headers=as_user(peer, org))).status_code == 403
    assert (await client.post(approve, json={}, headers=as_user(emp, org))).status_code == 403
    # Another org can't even see it exists.
    assert (
        await client.post(approve, json={}, headers=as_user(stranger, other_org))
    ).status_code == 404
    cancel = f"{LEAVE}/requests/{request_id}/cancel"
    assert (await client.post(cancel, headers=as_user(mgr, org))).status_code == 403
    assert (await client.post(cancel, headers=as_user(stranger, other_org))).status_code == 404

    approved = await client.post(approve, json={}, headers=as_user(mgr, org))
    assert approved.status_code == 200
    assert approved.json()["status"] == "approved"
    again = await client.post(approve, json={}, headers=as_user(mgr, org))
    assert again.status_code == 409


async def test_balances_are_for_self_managers_and_hr_only(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, mgr, peer, hr, admin), _ = await setup_org(
        pg_session_factory, "Emp", "Mgr", "Peer", "Hr", "Admin"
    )
    other_org, (stranger,), _ = await setup_org(pg_session_factory, "Stranger")
    await report_to(pg_session_factory, org, emp, mgr)
    await give_role(pg_session_factory, org, hr, "hr")
    # admin can configure leave but isn't HR: per-type usage would reveal sick leave.
    await give_role(pg_session_factory, org, admin, "admin")
    url = f"{LEAVE}/balances/{emp}"
    for viewer, expected in ((emp, 200), (mgr, 200), (hr, 200), (peer, 403), (admin, 403)):
        response = await client.get(url, headers=as_user(viewer, org))
        assert response.status_code == expected, (viewer, response.text)
    outsider = await client.get(f"{LEAVE}/balances/{stranger}", headers=as_user(hr, org))
    assert outsider.status_code == 404
    assert (await client.get(url, headers=as_user(stranger, other_org))).status_code == 404


async def test_policy_admin_routes_need_leave_configure(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (member, admin), _ = await setup_org(pg_session_factory, "Member", "Admin")
    await give_role(pg_session_factory, org, admin, "admin")
    for path in ("/policies", "/holiday-countries"):
        assert (await client.get(LEAVE + path, headers=as_user(member, org))).status_code == 403
        assert (await client.get(LEAVE + path, headers=as_user(admin, org))).status_code == 200


async def test_nobody_but_the_owner_changes_their_own_leave(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr, owner), casual = await setup_org(pg_session_factory, "Hr", "Owner")
    await give_role(pg_session_factory, org, hr, "hr")
    await give_role(pg_session_factory, org, owner, "org_owner")
    async with pg_session_factory() as db:
        policy_id = (await resolve_member_policy(db, org, hr)).policy.id
    adjust = {"leave_type_id": str(casual), "days": "2", "note": "Carry forward"}
    for user, expected in ((hr, 403), (owner, 200)):
        own = await client.post(
            f"{LEAVE}/balances/{user}/adjust", json=adjust, headers=as_user(user, org)
        )
        assert own.status_code == expected, own.text
        move = await client.post(
            f"{LEAVE}/policies/{policy_id}/assign",
            json={"user_ids": [str(user)]},
            headers=as_user(user, org),
        )
        assert move.status_code == expected, move.text


async def test_people_responses_are_never_cached(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp,), _ = await setup_org(pg_session_factory, "Emp")
    response = await client.get(f"{LEAVE}/me/summary", headers=as_user(emp, org))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, private"


async def test_a_request_spanning_years_is_rejected_before_any_work(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp,), casual = await setup_org(pg_session_factory, "Emp")
    body = {
        "kind": "leave",
        "leave_type_id": str(casual),
        "start_date": "0001-01-01",
        "end_date": future_monday().isoformat(),
    }
    response = await client.post(f"{LEAVE}/requests/preview", json=body, headers=as_user(emp, org))
    assert response.status_code == 422
