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

"""Design systems: who may change them, and which org's they are.

Reading needs ``settings:view`` (developers have it); every write needs
``settings:edit``. Another org's design system reads as not found to
every route, and the default flag only ever moves within one org.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from httpx import AsyncClient

from app.models.design_system import DesignSystemRef
from tests.integration.settings_support import Factory, add_tracked_repo, make_org

pytestmark = pytest.mark.integration

DS = "/api/v1/design-systems"


async def _design_system(factory: Factory, org_id: uuid.UUID, *, default: bool) -> uuid.UUID:
    repo_id = await add_tracked_repo(factory, org_id, f"/srv/{uuid.uuid4().hex}/web")
    async with factory() as db:
        ds = DesignSystemRef(
            org_id=org_id,
            repo_id=repo_id,
            is_default=default,
            content=":root { --brand: #123456; }",
            extracted_at=datetime.now(UTC),
        )
        db.add(ds)
        await db.commit()
        return ds.id


async def _row(factory: Factory, ds_id: uuid.UUID) -> DesignSystemRef | None:
    async with factory() as db:
        return await db.get(DesignSystemRef, ds_id)


async def test_another_orgs_design_system_is_not_found_everywhere(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    owner_org, other = await make_org(pg_session_factory), await make_org(pg_session_factory)
    ds_id = await _design_system(pg_session_factory, owner_org.id, default=True)
    headers = other.owner.headers

    attempts = [
        await client.get(f"{DS}/{ds_id}", headers=headers),
        await client.put(f"{DS}/{ds_id}", headers=headers, json={"custom_content": "x"}),
        await client.post(f"{DS}/{ds_id}/reset-customisations", headers=headers),
        await client.post(f"{DS}/set-default", headers=headers, json={"id": str(ds_id)}),
        await client.delete(f"{DS}/{ds_id}", headers=headers),
    ]

    assert [r.status_code for r in attempts] == [404] * len(attempts)
    row = await _row(pg_session_factory, ds_id)
    assert row is not None
    assert (row.is_default, row.custom_content) == (True, None)
    listed = await client.get(f"{DS}/", headers=headers)
    assert listed.json() == []


async def test_a_developer_reads_but_cannot_change(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await make_org(pg_session_factory)
    ds_id = await _design_system(pg_session_factory, org.id, default=False)
    headers = org.developer.headers

    read = await client.get(f"{DS}/{ds_id}", headers=headers)
    writes = [
        await client.put(f"{DS}/{ds_id}", headers=headers, json={"custom_content": "x"}),
        await client.post(f"{DS}/set-default", headers=headers, json={"id": str(ds_id)}),
        await client.delete(f"{DS}/{ds_id}", headers=headers),
        await client.post(f"{DS}/extract", headers=headers, json={"repo_id": str(uuid.uuid4())}),
    ]

    assert read.status_code == 200
    assert [r.status_code for r in writes] == [403] * len(writes)
    assert await _row(pg_session_factory, ds_id) is not None


async def test_set_default_moves_the_flag_within_one_org_only(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, other = await make_org(pg_session_factory), await make_org(pg_session_factory)
    first = await _design_system(pg_session_factory, org.id, default=True)
    second = await _design_system(pg_session_factory, org.id, default=False)
    elsewhere = await _design_system(pg_session_factory, other.id, default=True)

    response = await client.post(
        f"{DS}/set-default", headers=org.owner.headers, json={"id": str(second)}
    )

    assert response.status_code == 204
    flags = [(await _row(pg_session_factory, i)) for i in (first, second, elsewhere)]
    assert [f.is_default for f in flags if f] == [False, True, True]


async def test_customisation_round_trip_and_reset(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await make_org(pg_session_factory)
    ds_id = await _design_system(pg_session_factory, org.id, default=False)
    headers = org.owner.headers

    saved = await client.put(
        f"{DS}/{ds_id}", headers=headers, json={"custom_content": ":root { --brand: red; }"}
    )
    blank = await client.put(f"{DS}/{ds_id}", headers=headers, json={"custom_content": "   "})
    await client.put(f"{DS}/{ds_id}", headers=headers, json={"custom_content": "kept"})
    reset = await client.post(f"{DS}/{ds_id}/reset-customisations", headers=headers)

    assert saved.status_code == 200, saved.text
    assert saved.json()["custom_content"] == ":root { --brand: red; }"
    assert blank.json()["custom_content"] is None
    assert reset.status_code == 204
    row = await _row(pg_session_factory, ds_id)
    assert row is not None
    assert (row.custom_content, row.content) == (None, ":root { --brand: #123456; }")


async def test_extract_for_another_orgs_repo_is_not_found(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, other = await make_org(pg_session_factory), await make_org(pg_session_factory)
    repo_id = await add_tracked_repo(pg_session_factory, other.id, f"/srv/{uuid.uuid4().hex}/w")
    response = await client.post(
        f"{DS}/extract", headers=org.owner.headers, json={"repo_id": str(repo_id)}
    )
    assert response.status_code == 404
