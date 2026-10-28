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

"""``/buds/{id}/linked-features`` against real Postgres.

Manual links are idempotent, deduplicated and recorded on the timeline.
Features from another org and inactive features never get linked, and a
BUD from another org is a 404 on every verb.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.feature import Feature
from tests.integration.bud_lifecycle_reads import (
    timeline,
)
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_member,
    as_user,
    new_org,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration


async def _feature(factory: Factory, org: uuid.UUID, title: str, *, active: bool = True) -> str:
    """Create a registry feature and return its id as a string."""
    async with factory() as db:
        feature = Feature(
            org_id=org,
            feature_title=title,
            description=title,
            capabilities={"capabilities": []},
            cluster_names=[],
            tags=[],
            cluster_signature=f"sig:{uuid.uuid4().hex}",
            is_active=active,
        )
        db.add(feature)
        await db.commit()
        return str(feature.id)


async def _setup(factory: Factory) -> tuple[uuid.UUID, uuid.UUID, dict[str, str]]:
    """Org, a BUD in it and a PM's auth headers."""
    org = await new_org(factory)
    pm = await add_member(factory, org, "pm")
    bud_id = await add_bud(factory, org)
    return org, bud_id, as_user(pm, org)


async def test_link_list_unlink_round_trip(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Duplicates collapse, relinking inserts nothing, unlink removes and logs."""
    org, bud_id, headers = await _setup(pg_session_factory)
    login = await _feature(pg_session_factory, org, "Login")
    billing = await _feature(pg_session_factory, org, "Billing")
    url = f"/api/v1/buds/{bud_id}/linked-features"

    first = await client.post(url, json={"featureIds": [login, login, billing]}, headers=headers)
    again = await client.post(url, json={"featureIds": [login]}, headers=headers)
    listed = await client.get(url, headers=headers)
    removed = await client.delete(f"{url}/{login}", headers=headers)
    removed_again = await client.delete(f"{url}/{login}", headers=headers)
    after = await client.get(url, headers=headers)

    assert (first.status_code, first.json()["insertedCount"]) == (201, 2)
    assert again.json()["insertedCount"] == 0
    assert [f["title"] for f in listed.json()] == ["Billing", "Login"]
    assert {f["source"] for f in listed.json()} == {"manual"}
    assert (removed.status_code, removed_again.status_code) == (204, 404)
    assert [f["title"] for f in after.json()] == ["Billing"]
    linked = await timeline(pg_session_factory, bud_id, "feature_linked")
    assert [e["count"] for e in linked] == [2]
    unlinked = await timeline(pg_session_factory, bud_id, "feature_unlinked")
    assert unlinked == [{"feature_id": login, "feature_title": "Login"}]


async def test_foreign_and_inactive_features_are_never_linked(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Another org's feature id and a soft-deleted feature are silently dropped."""
    org, bud_id, headers = await _setup(pg_session_factory)
    other_org = await new_org(pg_session_factory)
    foreign = await _feature(pg_session_factory, other_org, "Theirs")
    retired = await _feature(pg_session_factory, org, "Retired", active=False)
    url = f"/api/v1/buds/{bud_id}/linked-features"

    res = await client.post(url, json={"featureIds": [foreign, retired]}, headers=headers)

    assert (res.status_code, res.json()["insertedCount"]) == (201, 0)
    assert (await client.get(url, headers=headers)).json() == []
    assert await timeline(pg_session_factory, bud_id, "feature_linked") == []


async def test_other_org_bud_is_404_on_every_verb(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """An outsider can neither read, add nor remove links on the BUD."""
    org, bud_id, headers = await _setup(pg_session_factory)
    login = await _feature(pg_session_factory, org, "Login")
    url = f"/api/v1/buds/{bud_id}/linked-features"
    await client.post(url, json={"featureIds": [login]}, headers=headers)
    other_org = await new_org(pg_session_factory)
    outsider = as_user(await add_member(pg_session_factory, other_org, "outsider"), other_org)
    own_feature = await _feature(pg_session_factory, other_org, "Mine")

    read = await client.get(url, headers=outsider)
    add = await client.post(url, json={"featureIds": [own_feature]}, headers=outsider)
    remove = await client.delete(f"{url}/{login}", headers=outsider)

    assert (read.status_code, add.status_code, remove.status_code) == (404, 404, 404)
    assert [f["title"] for f in (await client.get(url, headers=headers)).json()] == ["Login"]


async def test_viewer_can_read_but_not_change_links(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Writes need buds:edit; empty bodies are rejected by the schema."""
    org, bud_id, headers = await _setup(pg_session_factory)
    login = await _feature(pg_session_factory, org, "Login")
    viewer = as_user(await add_member(pg_session_factory, org, "viewer", role="viewer"), org)
    url = f"/api/v1/buds/{bud_id}/linked-features"

    read = await client.get(url, headers=viewer)
    add = await client.post(url, json={"featureIds": [login]}, headers=viewer)
    empty = await client.post(url, json={"featureIds": []}, headers=headers)

    assert (read.status_code, add.status_code, empty.status_code) == (200, 403, 422)
    assert (await client.get(url, headers=headers)).json() == []
