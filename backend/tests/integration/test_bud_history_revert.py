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

"""BUD edit history and revert through the real routes.

A PATCH files the pre-edit BUD under the phase it happened in; revert
puts that content back and is itself recorded; a rejected PATCH leaves
no history; revert refuses once the BUD has moved past the snapshot's
phase or is closed; everything is org-scoped.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from httpx import AsyncClient

from app.models.bud import BUDDocument, BUDStatus
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


async def _edited_bud(
    client: AsyncClient, factory: Factory
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID, dict[str, str]]:
    """A BUD-phase BUD whose requirements were edited once through PATCH."""
    org = await new_org(factory)
    pm = await add_member(factory, org, "pm")
    bud_id = await add_bud(factory, org, requirements_md="original spec")
    headers = as_user(pm, org)
    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"requirements_md": "edited spec"}, headers=headers
        )
    assert res.status_code == 200
    return org, pm, bud_id, headers


async def _versions(client: AsyncClient, bud_id: uuid.UUID, headers: dict[str, str]) -> Any:
    """The History tab listing for the BUD."""
    res = await client.get(f"/api/v1/buds/{bud_id}/versions", headers=headers)
    assert res.status_code == 200
    return res.json()


async def test_patch_files_the_pre_edit_content(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """One edit -> one ``ui`` row in the bud phase holding the old text."""
    _org, pm, bud_id, headers = await _edited_bud(client, pg_session_factory)

    rows = await _versions(client, bud_id, headers)
    detail = await client.get(f"/api/v1/buds/{bud_id}/versions/bud/1", headers=headers)

    assert [(r["phase"], r["version_no"], r["source"]) for r in rows] == [("bud", 1, "ui")]
    assert rows[0]["edited_by"] == str(pm)
    assert detail.json()["snapshot"]["requirements_md"] == "original spec"


async def test_revert_restores_content_and_is_itself_revertible(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Revert writes the old text back, logs a revert row and a timeline event."""
    _org, _pm, bud_id, headers = await _edited_bud(client, pg_session_factory)

    with stub_externals() as ext:
        res = await client.post(f"/api/v1/buds/{bud_id}/revert/bud/1", headers=headers)

    assert res.status_code == 200
    assert res.json()["embedding_refreshed"] is True
    ext.embed.assert_awaited()
    assert (await load_bud(pg_session_factory, bud_id)).requirements_md == "original spec"
    rows = await _versions(client, bud_id, headers)
    assert sorted((r["version_no"], r["source"]) for r in rows) == [(1, "ui"), (2, "revert")]
    revert_detail = await client.get(f"/api/v1/buds/{bud_id}/versions/bud/2", headers=headers)
    # The revert row keeps what the revert replaced, so it can be undone.
    assert revert_detail.json()["snapshot"]["requirements_md"] == "edited spec"
    events = await timeline(pg_session_factory, bud_id, "content_updated")
    assert [e["snapshot_version_no"] for e in events if e.get("section") == "revert"] == [1]


async def test_rejected_patch_leaves_no_history(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """A 409 section-lock rejection must not write a version row."""
    org = await new_org(pg_session_factory)
    pm = await add_member(pg_session_factory, org, "pm")
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.DESIGN)
    headers = as_user(pm, org)

    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"requirements_md": "late edit"}, headers=headers
        )

    assert res.status_code == 409
    assert await _versions(client, bud_id, headers) == []


async def test_revert_refused_once_the_bud_has_moved_on(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """bud-phase content cannot be restored while the BUD is in design."""
    _org, _pm, bud_id, headers = await _edited_bud(client, pg_session_factory)

    with stub_externals():
        moved = await client.patch(
            f"/api/v1/buds/{bud_id}", json={"status": "design"}, headers=headers
        )
        res = await client.post(f"/api/v1/buds/{bud_id}/revert/bud/1", headers=headers)

    assert moved.status_code == 200
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "phase_progressed"
    assert (await load_bud(pg_session_factory, bud_id)).requirements_md == "edited spec"


async def test_revert_refused_on_a_closed_bud(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Closed is terminal for content too."""
    _org, _pm, bud_id, headers = await _edited_bud(client, pg_session_factory)
    async with pg_session_factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        bud.status = BUDStatus.CLOSED
        await db.commit()

    res = await client.post(f"/api/v1/buds/{bud_id}/revert/bud/1", headers=headers)

    assert res.status_code == 400
    assert (await load_bud(pg_session_factory, bud_id)).requirements_md == "edited spec"


async def test_unknown_version_is_404(client: AsyncClient, pg_session_factory: Factory) -> None:
    """Revert / detail of a version that does not exist is a 404."""
    _org, _pm, bud_id, headers = await _edited_bud(client, pg_session_factory)

    revert = await client.post(f"/api/v1/buds/{bud_id}/revert/bud/9", headers=headers)
    detail = await client.get(f"/api/v1/buds/{bud_id}/versions/design/1", headers=headers)

    assert (revert.status_code, detail.status_code) == (404, 404)


async def test_history_is_org_scoped_and_revert_needs_edit(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Outsiders get 404 everywhere; same-org QA can read history but not revert."""
    org, _pm, bud_id, _headers = await _edited_bud(client, pg_session_factory)
    other_org = await new_org(pg_session_factory)
    outsider = as_user(await add_member(pg_session_factory, other_org, "outsider"), other_org)
    qa = as_user(await add_member(pg_session_factory, org, "qa", role="qa"), org)

    with stub_externals():
        outsider_list = await client.get(f"/api/v1/buds/{bud_id}/versions", headers=outsider)
        outsider_detail = await client.get(
            f"/api/v1/buds/{bud_id}/versions/bud/1", headers=outsider
        )
        outsider_revert = await client.post(
            f"/api/v1/buds/{bud_id}/revert/bud/1", headers=outsider
        )
        qa_list = await client.get(f"/api/v1/buds/{bud_id}/versions", headers=qa)
        qa_revert = await client.post(f"/api/v1/buds/{bud_id}/revert/bud/1", headers=qa)

    assert (outsider_list.status_code, outsider_detail.status_code) == (404, 404)
    assert outsider_revert.status_code == 404
    assert (qa_list.status_code, qa_revert.status_code) == (200, 403)
    assert (await load_bud(pg_session_factory, bud_id)).requirements_md == "edited spec"
