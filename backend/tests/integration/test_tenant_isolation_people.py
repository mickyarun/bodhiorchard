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

"""Another org's members, roles, people data and leave are out of reach.

Users are global rows (membership lives in ``org_to_user``), so member
routes can't lean on a repository's ``org_id`` filter: each must check the
target belongs to the caller's org. The caller is org A's owner, so every
refusal here is tenant scoping, not a missing permission.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.repositories.role import RoleRepository
from app.services.employees import record_alerts
from app.services.leave import notify
from tests.integration.auth_tenancy_snapshot import member_state, snapshot
from tests.integration.auth_tenancy_support import Tenant, TenantRows, new_tenant, seed_rows
from tests.integration.leave_support import Factory, add_member_without_profile, as_user

pytestmark = pytest.mark.integration


@pytest.fixture(autouse=True)
def _no_background_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Leave decisions and record edits spawn Slack work on the app's own engine."""
    monkeypatch.setattr(notify, "spawn", lambda job: job.close())
    monkeypatch.setattr(record_alerts, "spawn", lambda job: job.close())


async def _viewer_role(factory: Factory) -> uuid.UUID:
    async with factory() as db:
        role = await RoleRepository(db).get_by_name_system("viewer")
        assert role is not None
        return role.id


# (method, path, json body, whether org B's dev rather than its owner makes it in-org)
Probe = tuple[str, str, dict[str, Any] | None, bool]


def _probes(b: Tenant, rows: TenantRows, viewer: uuid.UUID, merge_into: uuid.UUID) -> list[Probe]:
    """Probes aimed at org B's people and settings.

    ``merge_into`` is the member B's dev would be merged into.
    """
    member = f"/api/v1/members/{b.dev}"
    employee = f"/api/v1/employees/{b.dev}"
    leave = f"/api/v1/leave/requests/{rows.leave_request}"
    note = {"note": "Checked"}
    return [
        ("GET", f"/api/v1/roles/{rows.role}", None, False),
        ("PUT", f"/api/v1/roles/{rows.role}", {"name": "Taken over"}, False),
        ("DELETE", f"/api/v1/roles/{rows.role}", None, False),
        ("PATCH", f"{member}/role", {"roleId": str(viewer)}, False),
        ("PATCH", f"{member}/status", None, False),
        ("POST", f"{member}/set-password", None, False),
        ("PATCH", f"{member}/character", {"characterModel": None}, False),
        ("POST", f"/api/v1/members/{merge_into}/merge", {"sourceId": str(b.dev)}, False),
        ("POST", f"/api/v1/notifications/{rows.notification}/read", None, True),
        ("DELETE", f"/api/v1/notifications/{rows.notification}", None, True),
        ("PUT", f"/api/v1/offices/{rows.office}", {"name": "Taken over"}, False),
        ("DELETE", f"/api/v1/offices/{rows.office}", None, False),
        ("GET", employee, None, False),
        ("PUT", f"{employee}/work", {"designation": "Taken over"}, False),
        ("GET", f"{employee}/sensitive", None, False),
        ("GET", f"{employee}/documents", None, False),
        ("GET", f"{employee}/access-log", None, False),
        ("GET", f"{employee}/login", None, False),
        ("POST", f"{employee}/login/password", None, False),
        ("POST", f"{leave}/approve", note, False),
        ("POST", f"{leave}/reject", note, False),
        ("POST", f"{leave}/cancel", None, True),
        ("GET", f"/api/v1/organizations/{b.org}", None, False),
    ]


async def test_org_a_owner_cannot_touch_org_b_people(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    a = await new_tenant(pg_session_factory)
    b = await new_tenant(pg_session_factory)
    rows = await seed_rows(pg_session_factory, b)
    before = await snapshot(pg_session_factory, rows)
    dev_before = await member_state(pg_session_factory, b.dev, b.org)
    viewer = await _viewer_role(pg_session_factory)

    answers = {}
    for method, path, body, _by_dev in _probes(b, rows, viewer, a.dev):
        for caller in (a.owner, a.dev):
            headers = as_user(caller, a.org)
            response = await client.request(method, path, json=body, headers=headers)
            answers[f"{caller} {method} {path}"] = response.status_code
    # a.dev lacks most permissions, so only the owner's answers prove scoping;
    # neither may get anything but a refusal.
    owner_answers = {k: v for k, v in answers.items() if k.startswith(str(a.owner))}
    assert {k: v for k, v in owner_answers.items() if v != 404} == {}
    assert {k: v for k, v in answers.items() if v < 400} == {}
    assert await snapshot(pg_session_factory, rows) == before
    assert await member_state(pg_session_factory, b.dev, b.org) == dev_before


async def test_every_people_probe_succeeds_inside_its_own_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Control: writes included, so the 404s above are scoping and not bad requests.

    Each probe gets a fresh org so a delete or merge can't break the next one.
    """
    viewer = await _viewer_role(pg_session_factory)
    failed = {}
    for index in range(23):
        b = await new_tenant(pg_session_factory)
        rows = await seed_rows(pg_session_factory, b)
        # Merging needs a target without an employee record of its own.
        target = await add_member_without_profile(pg_session_factory, b.org, "Target")
        probes = _probes(b, rows, viewer, target)
        assert len(probes) == 23
        method, path, body, by_dev = probes[index]
        headers = as_user(b.dev if by_dev else b.owner, b.org)
        response = await client.request(method, path, json=body, headers=headers)
        if response.status_code >= 300:
            failed[f"{method} {path}"] = (response.status_code, response.text[:200])
    assert failed == {}


async def test_member_lists_and_directories_stay_in_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    a = await new_tenant(pg_session_factory)
    a_rows = await seed_rows(pg_session_factory, a)
    b = await new_tenant(pg_session_factory)
    b_rows = await seed_rows(pg_session_factory, b)
    headers = as_user(a.owner, a.org)
    expected = {
        "/api/v1/members": (a.dev, b.dev),
        "/api/v1/members/directory": (a.dev, b.dev),
        "/api/v1/employees": (a.dev, b.dev),
        "/api/v1/roles": (a_rows.role, b_rows.role),
        "/api/v1/offices": (a_rows.office, b_rows.office),
        "/api/v1/leave/approvals": (a_rows.leave_request, b_rows.leave_request),
    }
    for path, (own, foreign) in expected.items():
        response = await client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)
        assert str(own) in response.text, path
        assert str(foreign) not in response.text, path


async def test_notifications_belong_to_one_user_in_one_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Even the owner of the same org can't read or clear a colleague's notification."""
    a = await new_tenant(pg_session_factory)
    rows = await seed_rows(pg_session_factory, a)  # the notification is a.dev's
    owner = as_user(a.owner, a.org)
    listed_for_owner = await client.get("/api/v1/notifications/", headers=owner)
    assert str(rows.notification) not in listed_for_owner.text
    read = await client.post(f"/api/v1/notifications/{rows.notification}/read", headers=owner)
    assert read.status_code == 404
    dev = as_user(a.dev, a.org)
    listed = await client.get("/api/v1/notifications/", headers=dev)
    assert str(rows.notification) in listed.text
    mine = await client.post(f"/api/v1/notifications/{rows.notification}/read", headers=dev)
    assert mine.status_code == 200, mine.text
