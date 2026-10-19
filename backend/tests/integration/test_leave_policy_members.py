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

"""Who follows which leave policy, over real HTTP and real roles."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.services.leave.policies import resolve_member_policy
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
LEAVE = "/api/v1/leave"


async def _new_policy(client: AsyncClient, org: uuid.UUID, admin: uuid.UUID, name: str) -> str:
    response = await client.post(
        f"{LEAVE}/policies", json={"name": name}, headers=as_user(admin, org)
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def test_members_list_the_default_for_the_unassigned_and_filter_by_policy(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (admin, ana, ben), _ = await setup_org(pg_session_factory, "Admin", "Ana", "Ben")
    other_org, (stranger,), _ = await setup_org(pg_session_factory, "Stranger")
    await give_role(pg_session_factory, org, admin, "admin")
    await give_role(pg_session_factory, other_org, stranger, "admin")
    async with pg_session_factory() as db:
        default = (await resolve_member_policy(db, org, ana)).policy
    uk = await _new_policy(client, org, admin, "UK Office")
    moved = await client.post(
        f"{LEAVE}/policies/{uk}/assign", json={"user_ids": [str(ben)]}, headers=as_user(admin, org)
    )
    assert moved.status_code == 200, moved.text

    response = await client.get(f"{LEAVE}/policy-members", headers=as_user(admin, org))
    assert response.status_code == 200, response.text
    rows = {row["user_id"]: row for row in response.json()}
    # Another org's employees never show up.
    assert set(rows) == {str(admin), str(ana), str(ben)}
    assert rows[str(ana)]["policy_id"] == str(default.id)
    assert rows[str(ana)]["policy_name"] == default.name
    assert rows[str(ana)]["explicit"] is False
    assert rows[str(ben)]["policy_id"] == uk
    assert rows[str(ben)]["policy_name"] == "UK Office"
    assert rows[str(ben)]["explicit"] is True

    on_uk = await client.get(
        f"{LEAVE}/policy-members", params={"policy_id": uk}, headers=as_user(admin, org)
    )
    assert [row["user_id"] for row in on_uk.json()] == [str(ben)]
    on_default = await client.get(
        f"{LEAVE}/policy-members",
        params={"policy_id": str(default.id)},
        headers=as_user(admin, org),
    )
    assert {row["user_id"] for row in on_default.json()} == {str(admin), str(ana)}
    unassigned = await client.get(
        f"{LEAVE}/policy-members", params={"unassigned": "true"}, headers=as_user(admin, org)
    )
    assert {row["user_id"] for row in unassigned.json()} == {str(admin), str(ana)}
    first = await client.get(
        f"{LEAVE}/policy-members", params={"limit": 1}, headers=as_user(admin, org)
    )
    assert [row["name"] for row in first.json()] == ["Admin"]
    searched = await client.get(
        f"{LEAVE}/policy-members", params={"q": "an"}, headers=as_user(admin, org)
    )
    assert [row["user_id"] for row in searched.json()] == [str(ana)]
    # A policy from another org is not found, not silently empty.
    elsewhere = await client.get(
        f"{LEAVE}/policy-members",
        params={"policy_id": uk},
        headers=as_user(stranger, other_org),
    )
    assert elsewhere.status_code == 404


async def test_members_need_leave_configure(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (member,), _ = await setup_org(pg_session_factory, "Member")
    response = await client.get(f"{LEAVE}/policy-members", headers=as_user(member, org))
    assert response.status_code == 403


async def test_employee_record_shows_the_leave_policy_they_follow(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (admin, ana, ben), _ = await setup_org(pg_session_factory, "Admin", "Ana", "Ben")
    await give_role(pg_session_factory, org, admin, "admin")
    uk = await _new_policy(client, org, admin, "UK Office")
    await client.post(
        f"{LEAVE}/policies/{uk}/assign", json={"user_ids": [str(ben)]}, headers=as_user(admin, org)
    )

    ana_record = await client.get(f"/api/v1/employees/{ana}", headers=as_user(admin, org))
    assert ana_record.status_code == 200, ana_record.text
    implicit = ana_record.json()["leave_policy"]
    assert implicit["is_default"] is True
    assert implicit["explicit"] is False

    ben_record = await client.get(f"/api/v1/employees/{ben}", headers=as_user(admin, org))
    assert ben_record.json()["leave_policy"] == {
        "id": uk,
        "name": "UK Office",
        "is_default": False,
        "explicit": True,
    }
    # Their own record carries it too.
    own = await client.get("/api/v1/employees/me", headers=as_user(ben, org))
    assert own.json()["leave_policy"]["name"] == "UK Office"
