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

from typing import Any

import pytest
from httpx import AsyncClient

from tests.integration.auth_tenancy_snapshot import snapshot
from tests.integration.auth_tenancy_support import Tenant, TenantRows, new_tenant, seed_rows
from tests.integration.leave_support import Factory, as_user

pytestmark = pytest.mark.integration


def _writes(
    a: Tenant, mine: TenantRows, b: Tenant, theirs: TenantRows
) -> list[tuple[str, str, dict[str, Any]]]:
    """(method, own-row path, body naming one of org B's ids)."""
    return [
        ("POST", f"/api/v1/teams/{mine.team}/members", {"user_id": str(b.dev)}),
        ("POST", f"/api/v1/teams/{mine.team}/repos", {"repo_id": str(theirs.repo)}),
        ("PATCH", f"/api/v1/bugs/{mine.bug}", {"budId": str(theirs.bud)}),
        ("PATCH", f"/api/v1/bugs/{mine.bug}", {"featureId": str(theirs.feature)}),
        ("PATCH", f"/api/v1/members/{a.dev}/role", {"roleId": str(theirs.role)}),
        (
            "PUT",
            f"/api/v1/employees/{a.dev}/managers",
            {"managers": [{"user_id": str(b.dev), "is_primary": True}]},
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
    headers = as_user(a.owner, a.org)

    accepted = {}
    for method, path, body in _writes(a, mine, b, theirs):
        response = await client.request(method, path, json=body, headers=headers)
        if response.status_code < 400:
            accepted[f"{method} {path} {body}"] = response.status_code
    assert accepted == {}
    assert await snapshot(pg_session_factory, mine) == before


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
