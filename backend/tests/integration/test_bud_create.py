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

"""``POST /buds`` against real Postgres.

Numbers are per org and start at 1; the bug-linker embedding is stored
at creation (and a failing embedder never blocks creation); the planned
feature and the ``created`` timeline event come with every new BUD.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models.bud import BUDDocument, BUDStatus
from app.models.feature import Feature
from tests.integration.bud_lifecycle_reads import (
    load_bud,
    timeline,
)
from tests.integration.bud_lifecycle_support import (
    EMBEDDING_DIM,
    Factory,
    add_bud,
    add_member,
    as_user,
    new_org,
    stub_externals,
)

pytestmark = pytest.mark.integration


async def _create(
    client: AsyncClient, user: uuid.UUID, org: uuid.UUID, title: str
) -> dict[str, Any]:
    """Create a BUD as ``user`` and return the 201 body."""
    res = await client.post(
        "/api/v1/buds/",
        json={"title": title, "requirements_md": "Retry failed payments."},
        headers=as_user(user, org),
    )
    assert res.status_code == 201, res.text
    body: dict[str, Any] = res.json()
    return body


async def test_numbers_start_at_one_and_are_independent_per_org(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Two orgs each get BUD 1 then 2; neither sees the other's counter."""
    org_a, org_b = await new_org(pg_session_factory), await new_org(pg_session_factory)
    pm_a = await add_member(pg_session_factory, org_a, "pm-a")
    pm_b = await add_member(pg_session_factory, org_b, "pm-b")

    with stub_externals():
        a1 = await _create(client, pm_a, org_a, "A first")
        b1 = await _create(client, pm_b, org_b, "B first")
        a2 = await _create(client, pm_a, org_a, "A second")

    assert (a1["bud_number"], a2["bud_number"], b1["bud_number"]) == (1, 2, 1)
    assert a1["status"] == "bud"


async def test_numbering_continues_after_the_highest_existing_number(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Gaps (a deleted BUD 2) are not refilled: the next number is max + 1."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    await add_bud(pg_session_factory, org, number=1)
    await add_bud(pg_session_factory, org, number=3, status=BUDStatus.CLOSED)

    with stub_externals():
        created = await _create(client, pm, org, "Next")

    assert created["bud_number"] == 4


async def test_create_stores_embedding_feature_and_timeline(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """The embedder sees title + requirements; side rows reference BUD-001."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")

    with stub_externals() as ext:
        created = await _create(client, pm, org, "Payment retries")

    ext.embed.assert_any_await("Payment retries Retry failed payments.")
    bud = await load_bud(pg_session_factory, uuid.UUID(created["id"]))
    assert bud.embedding is not None and len(bud.embedding) == EMBEDDING_DIM
    async with pg_session_factory() as db:
        feature = await db.scalar(
            select(Feature).where(Feature.org_id == org, Feature.source_ref == "BUD-001")
        )
    assert feature is not None
    assert (feature.source, feature.feature_status, feature.is_active) == ("bud", "planned", True)
    created_events = await timeline(pg_session_factory, bud.id, "created")
    assert created_events == [{"source": "web"}]


async def test_embedding_failure_still_creates_the_bud(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """The bug-linker vector is best effort: no embedding, BUD still exists."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")

    with stub_externals() as ext:
        ext.embed.side_effect = RuntimeError("model unavailable")
        created = await _create(client, pm, org, "No vector")

    bud = await load_bud(pg_session_factory, uuid.UUID(created["id"]))
    assert bud.embedding is None
    assert bud.title == "No vector"


@pytest.mark.parametrize(
    "payload",
    [{"title": ""}, {"title": "x" * 501}, {}, {"title": "ok", "priority": "urgent"}],
)
async def test_invalid_payload_is_422_and_creates_nothing(
    client: AsyncClient, pg_session_factory: Factory, payload: dict[str, str]
) -> None:
    """Schema validation runs before numbering: no row is written."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")

    with stub_externals():
        res = await client.post("/api/v1/buds/", json=payload, headers=as_user(pm, org))

    assert res.status_code == 422
    async with pg_session_factory() as db:
        rows = await db.scalars(select(BUDDocument.id).where(BUDDocument.org_id == org))
        assert list(rows) == []


@pytest.mark.parametrize("role", ["viewer", "developer", "qa", None])
async def test_roles_without_create_permission_get_403(
    client: AsyncClient, pg_session_factory: Factory, role: str | None
) -> None:
    """buds:create is required; a role-less member falls back to minimal rights."""
    org = await new_org(pg_session_factory)
    user = await add_member(pg_session_factory, org, "nobody", role=role)

    res = await client.post("/api/v1/buds/", json={"title": "Nope"}, headers=as_user(user, org))

    assert res.status_code == 403


async def test_unicode_title_round_trips(client: AsyncClient, pg_session_factory: Factory) -> None:
    """Non-ASCII titles are stored and returned unchanged."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    title = "Café 決済 retries ✓"

    with stub_externals():
        created = await _create(client, pm, org, title)

    assert created["title"] == title
    assert (await load_bud(pg_session_factory, uuid.UUID(created["id"]))).title == title
