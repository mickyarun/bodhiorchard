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


"""Names can be fixed by the person themself or by HR, and nobody else."""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
BASE = "/api/v1/employees"


async def test_self_and_hr_can_fix_a_name_but_colleagues_cannot(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (emp, hr, dev), _ = await setup_org(pg_session_factory, "kannan-atoa", "Hr", "Dev")
    await give_role(pg_session_factory, org, hr, "hr")
    await give_role(pg_session_factory, org, dev, "developer")

    async def rename(who: object, whom: object, name: str) -> tuple[int, dict[str, object]]:
        r = await client.put(f"{BASE}/{whom}/name", json={"name": name}, headers=as_user(who, org))
        return r.status_code, r.json()

    # The record tells the UI who may edit.
    own = await client.get(f"{BASE}/{emp}", headers=as_user(emp, org))
    assert own.json()["access"]["edit_name"] is True
    status, body = await rename(emp, emp, "  Kannan   R  ")
    assert status == 200 and body["name"] == "Kannan R"  # spaces tidied
    status, body = await rename(hr, emp, "Kannan Rajendran")
    assert status == 200 and body["name"] == "Kannan Rajendran"
    status, body = await rename(dev, emp, "Someone else")
    assert status == 403 and "HR" in str(body["detail"])
    assert (await rename(emp, emp, "   "))[0] == 422


async def test_hr_cannot_rename_someone_outside_the_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr,), _ = await setup_org(pg_session_factory, "Hr")
    await give_role(pg_session_factory, org, hr, "hr")
    _other, (outsider,), _ = await setup_org(pg_session_factory, "Outsider")
    r = await client.put(
        f"{BASE}/{outsider}/name", json={"name": "Renamed"}, headers=as_user(hr, org)
    )
    assert r.status_code == 404
