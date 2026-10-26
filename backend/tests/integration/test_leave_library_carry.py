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

"""A library type's carry-forward cap is a shared rule, like its monthly limit."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient

from app.models.leave_type import LeaveType
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_library_support import add_policy, library_sick
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
BASE = "/api/v1/leave"


async def test_the_cap_reaches_every_policy_with_a_balance(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (hr,), _casual = await setup_org(pg_session_factory, "Hr")
    await give_role(pg_session_factory, org, hr, "hr")
    auth = as_user(hr, org)
    async with pg_session_factory() as db:
        default = (await ensure_default_policy(db, org)).id
    london = await add_policy(pg_session_factory, org, hr, "UK - London")
    entry = await library_sick(client, auth)
    linked = {}
    for policy, link in ((default, {}), (london, {"own_quota": True, "annual_quota_days": None})):
        url = f"{BASE}/policies/{policy}/library-types"
        added = await client.post(url, json={"template_id": entry, **link}, headers=auth)
        assert added.status_code == 201, added.text
        linked[policy] = uuid.UUID(added.json()["id"])

    edit = {"name": "Sick", "code": "SL", "annual_quota_days": "4", "carry_forward_days": "2"}
    saved = await client.put(f"{BASE}/library-types/{entry}", json=edit, headers=auth)
    assert saved.status_code == 200, saved.text
    assert Decimal(saved.json()["carry_forward_days"]) == Decimal(2)

    async with pg_session_factory() as db:
        on_default = await db.get(LeaveType, linked[default])
        on_london = await db.get(LeaveType, linked[london])
        assert on_default is not None and on_london is not None
        assert on_default.carry_forward_days == Decimal(2)
        # London keeps its own unlimited quota: no balance, so nothing to carry.
        assert on_london.carry_forward_days is None
