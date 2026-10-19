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

"""Offices and work arrangements over HTTP."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.leave_policy import LeavePolicy
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_custom_role,
    give_role,
    report_to,
    setup_org,
)

pytestmark = pytest.mark.integration
OFFICES = "/api/v1/offices"
EMPLOYEES = "/api/v1/employees"


async def _team(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, uuid.UUID]:
    org, (emp, hr, dev), _ = await setup_org(factory, "Emp", "Hr", "Dev")
    await give_role(factory, org, hr, "hr")
    await give_role(factory, org, dev, "developer")
    await report_to(factory, org, emp, hr)
    return org, emp, hr, dev


async def _uk_policy(factory: Factory, org: uuid.UUID) -> uuid.UUID:
    async with factory() as db:
        policy = LeavePolicy(org_id=org, name="UK", timezone="Europe/London")
        db.add(policy)
        await db.commit()
        return policy.id


async def _set_work(
    client: AsyncClient, org: uuid.UUID, hr: uuid.UUID, emp: uuid.UUID, **changes: Any
) -> dict[str, Any]:
    record = (await client.get(f"{EMPLOYEES}/{emp}", headers=as_user(hr, org))).json()
    work = {**record["work"], **changes}
    response = await client.put(f"{EMPLOYEES}/{emp}/work", json=work, headers=as_user(hr, org))
    assert response.status_code == 200, response.text
    return dict(response.json())


async def test_hr_manages_offices_and_anyone_lists_them(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, _emp, hr, dev = await _team(pg_session_factory)
    body = {"name": "London", "city": "London", "country_code": "gb"}
    assert (await client.post(OFFICES, json=body, headers=as_user(dev, org))).status_code == 403
    created = await client.post(OFFICES, json=body, headers=as_user(hr, org))
    assert created.status_code == 201, created.text
    assert created.json()[0]["country_code"] == "GB"
    again = await client.post(OFFICES, json={"name": "london"}, headers=as_user(hr, org))
    assert again.status_code == 409
    listed = await client.get(OFFICES, headers=as_user(dev, org))
    assert [o["name"] for o in listed.json()] == ["London"]


async def test_placing_someone_in_an_office_moves_them_to_its_policy(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    uk = await _uk_policy(pg_session_factory, org)
    office = (
        await client.post(
            OFFICES, json={"name": "London", "leave_policy_id": str(uk)}, headers=as_user(hr, org)
        )
    ).json()[0]
    record = await _set_work(client, org, hr, emp, office_id=office["id"])
    assert record["office"] == {"id": office["id"], "name": "London"}
    assert record["leave_policy"]["name"] == "UK" and record["leave_policy"]["explicit"]
    directory = (await client.get(EMPLOYEES, headers=as_user(hr, org))).json()
    assert next(e for e in directory if e["user_id"] == str(emp))["office"]["name"] == "London"
    # The office can't go while someone works there.
    delete = await client.delete(f"{OFFICES}/{office['id']}", headers=as_user(hr, org))
    assert delete.status_code == 409


async def test_remote_people_have_no_office_and_no_wfh(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    office = (
        await client.post(OFFICES, json={"name": "Chennai"}, headers=as_user(hr, org))
    ).json()[0]
    record = await _set_work(
        client, org, hr, emp, office_id=office["id"], work_arrangement="remote"
    )
    assert record["work"]["work_arrangement"] == "remote"
    assert record["work"]["office_id"] is None and record["office"] is None
    summary = (await client.get("/api/v1/leave/me/summary", headers=as_user(emp, org))).json()
    assert summary["work_arrangement"] == "remote"
    day = future_monday().isoformat()
    wfh = {"kind": "wfh", "start_date": day, "end_date": day}
    preview = await client.post(
        "/api/v1/leave/requests/preview", json=wfh, headers=as_user(emp, org)
    )
    assert [p["code"] for p in preview.json()["problems"]] == ["remote_no_wfh"]
    # Nobody works there now, so it can be deleted.
    gone = await client.delete(f"{OFFICES}/{office['id']}", headers=as_user(hr, org))
    assert gone.status_code == 204


async def test_another_orgs_office_is_refused(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, emp, hr, _dev = await _team(pg_session_factory)
    other, (other_hr,), _ = await setup_org(pg_session_factory, "OtherHr")
    await give_role(pg_session_factory, other, other_hr, "hr")
    theirs = (
        await client.post(OFFICES, json={"name": "Theirs"}, headers=as_user(other_hr, other))
    ).json()[0]
    record = (await client.get(f"{EMPLOYEES}/{emp}", headers=as_user(hr, org))).json()
    work = {**record["work"], "office_id": theirs["id"]}
    response = await client.put(f"{EMPLOYEES}/{emp}/work", json=work, headers=as_user(hr, org))
    assert response.status_code == 422


async def test_setting_an_offices_policy_needs_leave_rights(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, _emp, _hr, dev = await _team(pg_session_factory)
    uk = await _uk_policy(pg_session_factory, org)
    await give_custom_role(pg_session_factory, org, dev, "employees:manage", "employees:view")
    with_policy = {"name": "London", "leave_policy_id": str(uk)}
    refused = await client.post(OFFICES, json=with_policy, headers=as_user(dev, org))
    assert refused.status_code == 403
    office = (
        await client.post(OFFICES, json={"name": "London"}, headers=as_user(dev, org))
    ).json()[0]
    # Renaming without touching the policy is fine.
    renamed = await client.put(
        f"{OFFICES}/{office['id']}", json={"name": "London HQ"}, headers=as_user(dev, org)
    )
    assert renamed.status_code == 200
