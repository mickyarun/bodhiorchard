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

"""The library's own trail, and deleting a library type no policy uses."""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.leave_type import LeaveType
from app.services.leave.policies import ensure_default_policy
from tests.integration.leave_library_support import library_sick
from tests.integration.leave_support import Factory, as_user, give_role, setup_org

pytestmark = pytest.mark.integration
BASE = "/api/v1/leave"


async def _hr(factory: Factory) -> tuple[uuid.UUID, dict[str, str]]:
    org, (hr,), _casual = await setup_org(factory, "Hr")
    await give_role(factory, org, hr, "hr")
    return org, as_user(hr, org)


async def test_adding_changing_and_deleting_an_unused_type_is_traced(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _org, auth = await _hr(pg_session_factory)
    entry = await library_sick(client, auth)
    edit = {"name": "Sick leave", "code": "SL", "annual_quota_days": "6", "auto_approve": True}
    assert (await client.put(f"{BASE}/library-types/{entry}", json=edit, headers=auth)).is_success
    assert (await client.delete(f"{BASE}/library-types/{entry}", headers=auth)).status_code == 204
    assert (await client.get(f"{BASE}/library-types", headers=auth)).json() == []

    history = (await client.get(f"{BASE}/library-types/history", headers=auth)).json()
    assert [e["action"] for e in history] == [
        "library_type_deleted", "library_type_updated", "library_type_created"
    ]  # fmt: skip
    deleted, updated, created = (e["changes"] for e in history)
    assert deleted == {"library": "Sick leave"}
    assert updated["library"] == "Sick leave"
    assert updated["auto_approve"] == [False, True]
    assert updated["annual_quota_days"] == ["4", "6"]
    assert (created["library"], created["name"]) == ("Sick", [None, "Sick"])
    assert {e["actor"]["name"] for e in history} == {"Hr"}


async def test_a_type_in_use_is_kept_until_policies_stop_following_it(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, auth = await _hr(pg_session_factory)
    async with pg_session_factory() as db:
        policy = (await ensure_default_policy(db, org)).id
    entry = await library_sick(client, auth)
    added = await client.post(
        f"{BASE}/policies/{policy}/library-types", json={"template_id": entry}, headers=auth
    )
    type_id = added.json()["id"]
    # Switched off still counts: the type still follows the library.
    off = {"is_active": False}
    assert (await client.put(f"{BASE}/types/{type_id}/link", json=off, headers=auth)).is_success
    refused = await client.delete(f"{BASE}/library-types/{entry}", headers=auth)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"].startswith("Sick is still on Default.")

    assert (await client.delete(f"{BASE}/types/{type_id}/link", headers=auth)).is_success
    assert (await client.delete(f"{BASE}/library-types/{entry}", headers=auth)).status_code == 204
    async with pg_session_factory() as db:
        kept = await db.get(LeaveType, uuid.UUID(type_id))
        assert kept is not None and kept.template_id is None and kept.name == "Sick"


async def test_another_orgs_library_is_out_of_reach(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _org, auth = await _hr(pg_session_factory)
    entry = await library_sick(client, auth)
    _other, outsider = await _hr(pg_session_factory)
    gone = await client.delete(f"{BASE}/library-types/{entry}", headers=outsider)
    assert gone.status_code == 404
    assert (await client.get(f"{BASE}/library-types/history", headers=outsider)).json() == []
