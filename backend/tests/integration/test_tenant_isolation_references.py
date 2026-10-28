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

"""An org's own rows can't be pointed at another org's rows.

The row being written is the caller's, so it passes scoping; the id in
the body belongs to org B. Each write must be refused and leave org A's
rows unchanged, otherwise org B's people or data get pulled into org A.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.auth_tenancy_snapshot import member_state, snapshot
from tests.integration.auth_tenancy_support import Tenant, TenantRows, new_tenant, seed_rows
from tests.integration.leave_support import Factory, as_user

pytestmark = pytest.mark.integration


def _writes(
    a: Tenant, mine: TenantRows, user: uuid.UUID, rows: TenantRows
) -> list[tuple[str, str, dict[str, Any], int]]:
    """(method, own-row path, body naming ``user`` / ``rows``, status when foreign)."""
    return [
        ("POST", f"/api/v1/teams/{mine.team}/members", {"user_id": str(user)}, 400),
        ("POST", f"/api/v1/teams/{mine.team}/repos", {"repo_id": str(rows.repo)}, 400),
        ("PATCH", f"/api/v1/bugs/{mine.bug}", {"budId": str(rows.bud)}, 404),
        ("PATCH", f"/api/v1/bugs/{mine.bug}", {"featureId": str(rows.feature)}, 404),
        ("PATCH", f"/api/v1/members/{a.dev}/role", {"roleId": str(rows.role)}, 404),
        (
            "PUT",
            f"/api/v1/employees/{a.dev}/managers",
            {"managers": [{"user_id": str(user), "is_primary": True}]},
            400,
        ),
    ]


async def test_own_rows_cannot_reference_another_orgs_rows(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    a = await new_tenant(pg_session_factory)
    mine = await seed_rows(pg_session_factory, a)
    b = await new_tenant(pg_session_factory)
    theirs = await seed_rows(pg_session_factory, b)
    before = await snapshot(pg_session_factory, mine)
    dev_before = await member_state(pg_session_factory, a.dev, a.org)
    headers = as_user(a.owner, a.org)

    answers = {}
    for method, path, body, expected in _writes(a, mine, b.dev, theirs):
        response = await client.request(method, path, json=body, headers=headers)
        answers[f"{method} {path} {body}"] = (response.status_code, expected)
    assert {k: v for k, v in answers.items() if v[0] != v[1]} == {}
    assert await snapshot(pg_session_factory, mine) == before
    assert await member_state(pg_session_factory, a.dev, a.org) == dev_before


async def test_the_same_writes_with_own_ids_succeed(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Control: the bodies are well-formed, so the refusals above are scoping."""
    a = await new_tenant(pg_session_factory)
    mine = await seed_rows(pg_session_factory, a)
    headers = as_user(a.owner, a.org)
    for method, path, body, _foreign in _writes(a, mine, a.owner, mine):
        response = await client.request(method, path, json=body, headers=headers)
        assert response.status_code in (200, 201), (path, body, response.text)
    after = await member_state(pg_session_factory, a.dev, a.org)
    assert after["membership"]["role_id"] == mine.role
    assert after["managers"] == [str(a.owner)]


async def test_linking_another_orgs_feature_links_nothing(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Foreign feature ids are dropped silently (same as inactive ones)."""
    a = await new_tenant(pg_session_factory)
    mine = await seed_rows(pg_session_factory, a)
    b = await new_tenant(pg_session_factory)
    theirs = await seed_rows(pg_session_factory, b)
    headers = as_user(a.owner, a.org)
    path = f"/api/v1/buds/{mine.bud}/linked-features"
    linked = await client.post(path, json={"featureIds": [str(theirs.feature)]}, headers=headers)
    assert linked.status_code == 201, linked.text
    assert linked.json() == {"insertedCount": 0, "insertedFeatureIds": []}
    listed = await client.get(path, headers=headers)
    assert str(theirs.feature) not in listed.text
    own = await client.post(path, json={"featureIds": [str(mine.feature)]}, headers=headers)
    assert own.json()["insertedFeatureIds"] == [str(mine.feature)]
