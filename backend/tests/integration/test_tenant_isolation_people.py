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
from tests.integration.auth_tenancy_snapshot import member_state, snapshot
from tests.integration.auth_tenancy_support import Tenant, TenantRows, new_tenant, seed_rows
from tests.integration.leave_support import Factory, as_user

pytestmark = pytest.mark.integration


async def _viewer_role(factory: Factory) -> uuid.UUID:
    async with factory() as db:
        role = await RoleRepository(db).get_by_name_system("viewer")
        assert role is not None
        return role.id


def _probes(
    a: Tenant, b: Tenant, rows: TenantRows, viewer: uuid.UUID
) -> list[tuple[str, str, dict[str, Any] | None]]:
    """(method, path, json body) aimed at org B's people and settings."""
    member = f"/api/v1/members/{b.dev}"
    employee = f"/api/v1/employees/{b.dev}"
    leave = f"/api/v1/leave/requests/{rows.leave_request}"
    return [
        ("GET", f"/api/v1/roles/{rows.role}", None),
        ("PUT", f"/api/v1/roles/{rows.role}", {"name": "Taken over"}),
        ("DELETE", f"/api/v1/roles/{rows.role}", None),
        ("PATCH", f"{member}/role", {"roleId": str(viewer)}),
        ("PATCH", f"{member}/status", None),
        ("POST", f"{member}/set-password", None),
        ("PATCH", f"{member}/character", {"characterModel": None}),
        ("POST", f"/api/v1/members/{a.dev}/merge", {"sourceId": str(b.dev)}),
        ("POST", f"/api/v1/notifications/{rows.notification}/read", None),
        ("DELETE", f"/api/v1/notifications/{rows.notification}", None),
        ("PUT", f"/api/v1/offices/{rows.office}", {"name": "Taken over"}),
        ("DELETE", f"/api/v1/offices/{rows.office}", None),
        ("GET", employee, None),
        ("PUT", f"{employee}/work", {"designation": "Taken over"}),
        ("GET", f"{employee}/sensitive", None),
        ("GET", f"{employee}/documents", None),
        ("GET", f"{employee}/access-log", None),
        ("GET", f"{employee}/login", None),
        ("POST", f"{employee}/login/password", None),
        ("POST", f"{leave}/approve", {}),
        ("POST", f"{leave}/reject", {}),
        ("POST", f"{leave}/cancel", None),
        ("GET", f"/api/v1/organizations/{b.org}", None),
    ]


async def test_org_a_owner_cannot_touch_org_b_people(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    a = await new_tenant(pg_session_factory)
    b = await new_tenant(pg_session_factory)
    rows = await seed_rows(pg_session_factory, b)
    before = await snapshot(pg_session_factory, rows)
    dev_before = await member_state(pg_session_factory, b.dev, b.org)
    headers = as_user(a.owner, a.org)

    answers = {}
    for method, path, body in _probes(a, b, rows, await _viewer_role(pg_session_factory)):
        response = await client.request(method, path, json=body, headers=headers)
        answers[f"{method} {path}"] = response.status_code
    assert {k: v for k, v in answers.items() if v != 404} == {}
    assert await snapshot(pg_session_factory, rows) == before
    assert await member_state(pg_session_factory, b.dev, b.org) == dev_before


async def test_org_b_owner_reaches_the_same_people(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Control: the read probes work in their own org, so the 404s above are scoping."""
    a = await new_tenant(pg_session_factory)
    b = await new_tenant(pg_session_factory)
    rows = await seed_rows(pg_session_factory, b)
    headers = as_user(b.owner, b.org)
    probes = _probes(a, b, rows, await _viewer_role(pg_session_factory))
    for _method, path, _body in (p for p in probes if p[0] == "GET"):
        response = await client.get(path, headers=headers)
        assert response.status_code == 200, (path, response.text)


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
    assert mine.status_code in (200, 204), mine.text
