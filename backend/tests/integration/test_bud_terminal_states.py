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

"""Closed and discarded BUDs through the real PATCH / restore routes.

Closed is irreversible: no status change out of it, a second close is
rejected, and restore refuses it. Discarded is recoverable only through
``POST /buds/{id}/restore``. Every rejection must leave the row and the
timeline untouched.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from tests.integration.bud_lifecycle_reads import (
    load_bud,
    timeline,
)
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_member,
    as_user,
    new_org,
    stub_externals,
)
from tests.integration.bud_lifecycle_support import (
    app_database_blocked as app_database_blocked,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize(
    "target", [BUDStatus.BUD, BUDStatus.PROD, BUDStatus.CLOSED, BUDStatus.DISCARDED]
)
async def test_closed_bud_rejects_every_status_change(
    client: AsyncClient, pg_session_factory: Factory, target: BUDStatus
) -> None:
    """A closed BUD stays closed, including a second close."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.CLOSED)

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": target.value}, headers=as_user(pm, org)
        )

    assert res.status_code == 400
    assert "Cannot change status of a closed BUD" in res.json()["detail"]
    assert "Create a new BUD instead" in res.json()["detail"]
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.CLOSED
    assert await timeline(pg_session_factory, bud_id, "status_change") == []


async def test_discarded_bud_points_to_restore_instead_of_patch(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """PATCHing a discarded BUD's status is refused with the restore hint."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.DISCARDED)

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "development"}, headers=as_user(pm, org)
        )

    assert res.status_code == 400
    assert "Use the restore action" in res.json()["detail"]
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.DISCARDED


async def test_closed_bud_title_stays_editable(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Only status is frozen on a closed BUD; the title is not a phase-owned field."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.CLOSED)

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"title": "Renamed"}, headers=as_user(pm, org)
        )

    assert res.status_code == 200
    bud = await load_bud(pg_session_factory, bud_id)
    assert (bud.title, bud.status) == ("Renamed", BUDStatus.CLOSED)


async def test_closed_bud_requirements_are_locked(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Phase-owned sections cannot be rewritten after close (409 section lock)."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(
        pg_session_factory, org, status=BUDStatus.CLOSED, requirements_md="shipped spec"
    )

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}",
            json={"requirements_md": "rewritten"},
            headers=as_user(pm, org),
        )

    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "bud_section_locked"
    assert (await load_bud(pg_session_factory, bud_id)).requirements_md == "shipped spec"


@pytest.mark.parametrize("status", [BUDStatus.CLOSED, BUDStatus.DEVELOPMENT])
async def test_restore_refuses_anything_not_discarded(
    client: AsyncClient, pg_session_factory: Factory, status: BUDStatus
) -> None:
    """Restore is for discarded BUDs only; closed in particular stays terminal."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=status)

    res = await client.post(f"/api/v1/buds/{bud_id}/restore", headers=as_user(pm, org))

    assert res.status_code == 409
    assert (await load_bud(pg_session_factory, bud_id)).status is status


async def test_discard_then_restore_round_trip_through_the_api(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Discard via PATCH, restore via POST: the BUD lands back in its old phase."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.CODE_REVIEW)
    headers = as_user(pm, org)

    with stub_externals():
        discard = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "discarded"}, headers=headers
        )
        assert discard.status_code == 200
        restored = await client.post(f"/api/v1/buds/{bud_id}/restore", headers=headers)
        again = await client.post(f"/api/v1/buds/{bud_id}/restore", headers=headers)

    assert restored.status_code == 200
    assert restored.json()["status"] == "code_review"
    # A second restore finds a live BUD and refuses.
    assert again.status_code == 409
    changes = await timeline(pg_session_factory, bud_id, "status_change")
    assert sorted((c["from"], c["to"]) for c in changes) == [
        ("code_review", "discarded"),
        ("discarded", "code_review"),
    ]


async def test_qa_cannot_restore_a_discarded_bud(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Restore needs buds:edit; the QA role (buds:test) gets 403."""
    org = await new_org(pg_session_factory)
    qa = await add_member(pg_session_factory, org, "qa", role="qa")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.DISCARDED)

    res = await client.post(f"/api/v1/buds/{bud_id}/restore", headers=as_user(qa, org))

    assert res.status_code == 403
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.DISCARDED


async def test_other_org_cannot_close_or_restore(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A PM of another org sees 404 on both routes and changes nothing."""
    owner_org = await new_org(pg_session_factory)
    other_org = await new_org(pg_session_factory)
    outsider = await add_member(pg_session_factory, other_org, "outsider")
    live = await add_bud(pg_session_factory, owner_org, status=BUDStatus.TESTING)
    binned = await add_bud(pg_session_factory, owner_org, number=2, status=BUDStatus.DISCARDED)
    headers = as_user(outsider, other_org)

    with stub_externals():
        close = await client.patch(
            f"/api/v1/buds/{live}", json={"status": "closed"}, headers=headers
        )
        restore = await client.post(f"/api/v1/buds/{binned}/restore", headers=headers)

    assert (close.status_code, restore.status_code) == (404, 404)
    assert (await load_bud(pg_session_factory, live)).status is BUDStatus.TESTING
    assert (await load_bud(pg_session_factory, binned)).status is BUDStatus.DISCARDED


async def test_unknown_status_is_a_400(client: AsyncClient, pg_session_factory: Factory) -> None:
    """A status outside the enum is rejected before any side effect."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.TESTING)

    res = await client.patch(
        f"/api/v1/buds/{bud_id}", json={"status": "shipped"}, headers=as_user(pm, org)
    )

    assert res.status_code == 400
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.TESTING
