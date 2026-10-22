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

"""The leave type library: define once, add to policies, edit everywhere at once."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import NamedTuple

import pytest
from httpx import AsyncClient

from app.models.leave_config_event import LeaveConfigAction
from app.models.leave_type import LeaveType
from app.models.leave_type_template import LeaveTypeTemplate
from app.repositories.leave_config_event import LeaveConfigEventRepository
from app.services.leave.lifecycle import submit
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_library_support import add_policy, library_sick
from tests.integration.leave_support import (
    Factory,
    as_user,
    future_monday,
    give_custom_role,
    give_role,
    leave_body,
    setup_org,
)

pytestmark = pytest.mark.integration
D = Decimal
BASE = "/api/v1/leave"


class Lib(NamedTuple):
    """HR's org with the default policy, a London policy and a Sick entry (4 days)."""

    org: uuid.UUID
    emp: uuid.UUID
    auth: dict[str, str]
    default: uuid.UUID
    london: uuid.UUID
    entry: str


async def _setup(client: AsyncClient, factory: Factory) -> Lib:
    org, (hr, emp), _casual = await setup_org(factory, "Hr", "Emp")
    await give_role(factory, org, hr, "hr")
    async with factory() as db:
        default = (await ensure_default_policy(db, org)).id
    london = await add_policy(factory, org, hr, "UK - London")
    entry = await library_sick(client, as_user(hr, org))
    return Lib(org, emp, as_user(hr, org), default, london, entry)


async def _add(client: AsyncClient, auth: dict[str, str], policy: uuid.UUID, entry: str,
               **link: object) -> dict[str, object]:  # fmt: skip
    url = f"{BASE}/policies/{policy}/library-types"
    response = await client.post(url, json={"template_id": entry, **link}, headers=auth)
    assert response.status_code == 201, response.text
    body: dict[str, object] = response.json()
    return body


async def test_library_edit_updates_every_policy_and_its_history(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, _emp, auth, default, london, entry = await _setup(client, pg_session_factory)
    follows = await _add(client, auth, default, entry)
    own = await _add(client, auth, london, entry, own_quota=True, annual_quota_days=None)
    assert (D(str(follows["annual_quota_days"])), follows["own_quota"]) == (D(4), False)
    assert (own["annual_quota_days"], own["stops_at_balance"]) == (None, False)
    again = await client.post(
        f"{BASE}/policies/{london}/library-types", json={"template_id": entry}, headers=auth
    )
    assert again.status_code == 409 and "already on this policy" in again.text

    edit = {"name": "Sick leave", "code": "SL", "annual_quota_days": "6",
            "stops_at_balance": True, "is_paid": False, "color_key": "swatch-3"}  # fmt: skip
    response = await client.put(f"{BASE}/library-types/{entry}", json=edit, headers=auth)
    assert response.status_code == 200, response.text
    assert {u["policy_name"] for u in response.json()["uses"]} == {"Default", "UK - London"}

    async with pg_session_factory() as db:
        on_default = await db.get(LeaveType, uuid.UUID(str(follows["id"])))
        on_london = await db.get(LeaveType, uuid.UUID(str(own["id"])))
        assert on_default is not None and on_london is not None
        assert (on_default.annual_quota_days, on_default.stops_at_balance) == (D(6), True)
        # London keeps its own unlimited quota, so it has no balance to stop at.
        assert (on_london.annual_quota_days, on_london.stops_at_balance) == (None, False)
        assert not on_default.is_paid and not on_london.is_paid
        assert on_london.color_key == "swatch-3"
        for policy in (default, london):
            events = await LeaveConfigEventRepository(db, org_id=org).for_policy(policy)
            change = events[0]
            assert change.action == LeaveConfigAction.TYPE_UPDATED
            assert change.changes["library"] == "Sick leave"
            assert change.changes["is_paid"] == [True, False]
            assert events[1].changes["library"] == [None, "Sick"]
            assert events[1].changes["own_quota"] == [None, policy == london]


async def test_on_a_policy_only_the_quota_and_switch_change(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _org, _emp, auth, default, _london, entry = await _setup(client, pg_session_factory)
    linked = await _add(client, auth, default, entry)
    url = f"{BASE}/types/{linked['id']}"
    edit = {"name": "Sick", "code": "SL", "annual_quota_days": "9", "is_paid": False}
    refused = await client.put(url, json=edit, headers=auth)
    assert refused.status_code == 409 and "leave type library" in refused.text

    own = {"own_quota": True, "annual_quota_days": "9", "is_active": False}
    response = await client.put(f"{url}/link", json=own, headers=auth)
    assert response.status_code == 200, response.text
    assert (D(response.json()["annual_quota_days"]), response.json()["is_paid"]) == (D(9), True)
    assert response.json()["is_active"] is False
    back = await client.put(f"{url}/link", json={"annual_quota_days": "9"}, headers=auth)
    assert (D(back.json()["annual_quota_days"]), back.json()["own_quota"]) == (D(4), False)


async def test_only_approvers_make_a_library_type_approve_itself(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, (admin,), _casual = await setup_org(pg_session_factory, "Admin")
    await give_custom_role(pg_session_factory, org, admin, "leave:configure")
    auth = as_user(admin, org)
    body = {"name": "Period", "code": "PL", "annual_quota_days": "12", "auto_approve": True}
    refused = await client.post(f"{BASE}/library-types", json=body, headers=auth)
    assert refused.status_code == 403, refused.text
    body["auto_approve"] = False
    assert (await client.post(f"{BASE}/library-types", json=body, headers=auth)).status_code == 201
    again = await client.post(f"{BASE}/library-types", json=body, headers=auth)
    assert again.status_code == 409 and "already used in the library" in again.text


async def test_a_self_approving_entry_needs_a_quota_on_every_policy(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _org, _emp, auth, default, london, entry = await _setup(client, pg_session_factory)
    await _add(client, auth, default, entry)
    await _add(client, auth, london, entry, own_quota=True, annual_quota_days=None)
    edit = {"name": "Sick", "code": "SL", "annual_quota_days": "4", "auto_approve": True}
    refused = await client.put(f"{BASE}/library-types/{entry}", json=edit, headers=auth)
    assert refused.status_code == 422, refused.text
    assert refused.json()["detail"].startswith("On UK - London: A type that approves itself")


async def test_accrual_change_is_refused_naming_the_policy_in_use(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, emp, auth, default, london, entry = await _setup(client, pg_session_factory)
    await _add(client, auth, default, entry)
    on_london = await _add(client, auth, london, entry)
    await client.post(f"{BASE}/policies/{london}/assign", json={"user_ids": [str(emp)]},
                      headers=auth)  # fmt: skip
    mon = future_monday()
    async with pg_session_factory() as db:
        await submit(db, org, emp, leave_body(uuid.UUID(str(on_london["id"])), mon, mon))
        await db.commit()
    edit = {"name": "Sick", "code": "SL", "annual_quota_days": "4", "accrual": "monthly"}
    refused = await client.put(f"{BASE}/library-types/{entry}", json=edit, headers=auth)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"].startswith("On UK - London: This type is already in use")
    async with pg_session_factory() as db:
        template = await db.get(LeaveTypeTemplate, uuid.UUID(entry))
        assert template is not None and template.accrual.value == "upfront"
