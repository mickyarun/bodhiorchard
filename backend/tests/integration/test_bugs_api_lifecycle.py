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

"""Filing and moving bugs through the API: links, numbering and status stamps."""

from __future__ import annotations

import asyncio
import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.api.v1 import bugs as bugs_api
from app.models.bud import BUDStatus
from app.models.bug import Bug
from app.services import bug_linker
from tests.integration.scan_features_bugs_support import (
    Factory,
    as_user,
    new_bud,
    new_feature,
    new_member,
    new_org,
    vec,
)

pytestmark = pytest.mark.integration

BUGS = "/api/v1/bugs"
BUG_VECTOR = vec(1)


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory) -> None:
    """Fake the model and point the background embedder at the test database."""

    async def _embed(text: str) -> list[float]:
        return BUG_VECTOR

    fake = SimpleNamespace(embed=_embed)
    monkeypatch.setattr(bug_linker, "embedding_service", fake)
    monkeypatch.setattr(bugs_api, "embedding_service", fake)
    monkeypatch.setattr(bugs_api, "AsyncSessionLocal", pg_session_factory)


async def _setup(factory: Factory, role: str = "manager") -> tuple[uuid.UUID, dict[str, str]]:
    org = await new_org(factory)
    return org, as_user(await new_member(factory, org, role), org)


async def test_a_new_bug_is_auto_linked_to_the_matching_bud(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, headers = await _setup(pg_session_factory)
    bud = await new_bud(pg_session_factory, org, 4, embedding=BUG_VECTOR)

    resp = await client.post(BUGS, json={"title": "Cart total wrong"}, headers=headers)

    assert resp.status_code == 201
    body = resp.json()
    assert body["budId"] == str(bud)
    assert body["budNumber"] == 4
    assert body["bugType"] == "testing"
    assert body["status"] == "open"


async def test_a_new_bug_with_a_feature_is_production_and_embedded_in_the_background(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, headers = await _setup(pg_session_factory)
    feature = await new_feature(pg_session_factory, org, "Cart")

    resp = await client.post(
        BUGS, json={"title": "Cart total wrong", "featureId": str(feature)}, headers=headers
    )
    await asyncio.gather(*bugs_api._background_tasks)

    body = resp.json()
    assert body["bugType"] == "production"
    assert body["featureTitle"] == "Cart"
    async with pg_session_factory() as db:
        stored = await db.get(Bug, uuid.UUID(body["id"]))
        assert stored is not None and stored.embedding is not None


async def test_a_bud_already_in_uat_makes_the_bug_a_production_bug(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, headers = await _setup(pg_session_factory)
    bud = await new_bud(pg_session_factory, org, 1, status=BUDStatus.UAT)
    resp = await client.post(BUGS, json={"title": "x", "budId": str(bud)}, headers=headers)
    await asyncio.gather(*bugs_api._background_tasks)
    assert resp.json()["bugType"] == "production"


async def test_bug_numbers_count_up_per_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org_a, headers_a = await _setup(pg_session_factory)
    _, headers_b = await _setup(pg_session_factory)

    numbers_a = [
        (await client.post(BUGS, json={"title": f"a{i}"}, headers=headers_a)).json()["bugNumber"]
        for i in range(3)
    ]
    first_b = (await client.post(BUGS, json={"title": "b"}, headers=headers_b)).json()

    assert numbers_a == [1, 2, 3]
    assert first_b["bugNumber"] == 1


async def test_resolved_at_is_stamped_once_and_kept_on_later_moves(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, headers = await _setup(pg_session_factory)
    bug_id = (await client.post(BUGS, json={"title": "x"}, headers=headers)).json()["id"]

    resolved = (
        await client.patch(f"{BUGS}/{bug_id}", json={"status": "resolved"}, headers=headers)
    ).json()
    closed = (
        await client.patch(f"{BUGS}/{bug_id}", json={"status": "closed"}, headers=headers)
    ).json()

    assert resolved["resolvedAt"] is not None
    assert closed["resolvedAt"] == resolved["resolvedAt"]


async def test_rejecting_a_bug_stamps_rejected_at_in_the_database(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, headers = await _setup(pg_session_factory)
    bug_id = (await client.post(BUGS, json={"title": "x"}, headers=headers)).json()["id"]

    resp = await client.patch(f"{BUGS}/{bug_id}", json={"status": "rejected"}, headers=headers)

    assert resp.status_code == 200
    assert resp.json()["resolvedAt"] is None
    async with pg_session_factory() as db:
        stored = await db.get(Bug, uuid.UUID(bug_id))
        assert stored is not None and stored.rejected_at is not None


async def test_the_board_defaults_to_production_bugs(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, headers = await _setup(pg_session_factory)
    feature = await new_feature(pg_session_factory, org, "Cart")
    await client.post(BUGS, json={"title": "t"}, headers=headers)
    await client.post(BUGS, json={"title": "p", "featureId": str(feature)}, headers=headers)
    await asyncio.gather(*bugs_api._background_tasks)

    default = (await client.get(f"{BUGS}/board", headers=headers)).json()
    everything = (await client.get(f"{BUGS}/board?bugType=all", headers=headers)).json()

    assert [b["title"] for b in default["columns"]["open"]] == ["p"]
    assert everything["total"] == 2
    assert set(default["columns"]) == {
        "open", "in-progress", "resolved", "closed", "blocked", "rejected"
    }  # fmt: skip


async def test_list_filters_by_status_and_pages(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, headers = await _setup(pg_session_factory)
    ids = [
        (await client.post(BUGS, json={"title": f"b{i}"}, headers=headers)).json()["id"]
        for i in range(3)
    ]
    await client.patch(f"{BUGS}/{ids[0]}", json={"status": "closed"}, headers=headers)

    open_bugs = (await client.get(f"{BUGS}?status=open", headers=headers)).json()
    page = (await client.get(f"{BUGS}?pageSize=1&page=2", headers=headers)).json()

    assert open_bugs["total"] == 2
    assert {b["id"] for b in open_bugs["items"]} == set(ids[1:])
    assert page["total"] == 3 and len(page["items"]) == 1
    too_big = await client.get(f"{BUGS}?pageSize=101", headers=headers)
    assert too_big.status_code == 422
