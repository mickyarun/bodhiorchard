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

"""Who may see and change bugs: org isolation and the per-action permissions."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

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


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Never load the real model; every bug embeds to the same vector."""

    async def _embed(text: str) -> list[float]:
        return vec(0, 1)

    monkeypatch.setattr(bug_linker, "embedding_service", SimpleNamespace(embed=_embed))


async def _file_bug(client: AsyncClient, headers: dict[str, str], **body: object) -> str:
    resp = await client.post(BUGS, json={"title": "Login fails", **body}, headers=headers)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test_another_orgs_bug_is_not_found_and_cannot_be_changed(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org_a, org_b = await new_org(pg_session_factory), await new_org(pg_session_factory)
    owner_a = as_user(await new_member(pg_session_factory, org_a, "manager"), org_a)
    owner_b = as_user(await new_member(pg_session_factory, org_b, "manager"), org_b)
    bug_id = await _file_bug(client, owner_a)

    assert (await client.get(f"{BUGS}/{bug_id}", headers=owner_b)).status_code == 404
    patch = await client.patch(f"{BUGS}/{bug_id}", json={"status": "closed"}, headers=owner_b)
    assert patch.status_code == 404
    listed = (await client.get(BUGS, headers=owner_b)).json()
    assert listed["total"] == 0
    board = (await client.get(f"{BUGS}/board?bugType=all", headers=owner_b)).json()
    assert board["total"] == 0
    still = (await client.get(f"{BUGS}/{bug_id}", headers=owner_a)).json()
    assert still["status"] == "open"


async def test_linking_to_another_orgs_bud_or_feature_on_update_is_refused(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org_a, org_b = await new_org(pg_session_factory), await new_org(pg_session_factory)
    headers = as_user(await new_member(pg_session_factory, org_a, "manager"), org_a)
    their_bud = await new_bud(pg_session_factory, org_b, 1)
    their_feature = await new_feature(pg_session_factory, org_b, "Theirs")
    bug_id = await _file_bug(client, headers)

    bud_patch = await client.patch(
        f"{BUGS}/{bug_id}", json={"budId": str(their_bud)}, headers=headers
    )
    feature_patch = await client.patch(
        f"{BUGS}/{bug_id}", json={"featureId": str(their_feature)}, headers=headers
    )

    assert bud_patch.status_code == 404
    assert feature_patch.status_code == 404
    body = (await client.get(f"{BUGS}/{bug_id}", headers=headers)).json()
    assert body["budId"] is None and body["featureId"] is None


async def test_a_member_outside_the_engineering_workspace_cannot_reach_bugs(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await new_org(pg_session_factory)
    headers = as_user(await new_member(pg_session_factory, org, "hr"), org)
    assert (await client.get(BUGS, headers=headers)).status_code == 403
    assert (await client.post(BUGS, json={"title": "x"}, headers=headers)).status_code == 403


async def test_a_member_without_a_role_files_bugs_as_a_developer(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Unassigned members get the developer permissions until an admin picks a role."""
    org = await new_org(pg_session_factory)
    headers = as_user(await new_member(pg_session_factory, org), org)
    bug_id = await _file_bug(client, headers)
    denied = await client.patch(f"{BUGS}/{bug_id}", json={"assigneeId": None}, headers=headers)
    assert denied.status_code == 403


async def test_a_viewer_can_read_but_not_file_or_edit(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await new_org(pg_session_factory)
    dev = as_user(await new_member(pg_session_factory, org, "developer"), org)
    viewer = as_user(await new_member(pg_session_factory, org, "viewer"), org)
    bug_id = await _file_bug(client, dev)

    assert (await client.get(f"{BUGS}/{bug_id}", headers=viewer)).status_code == 200
    assert (await client.post(BUGS, json={"title": "x"}, headers=viewer)).status_code == 403
    patch = await client.patch(f"{BUGS}/{bug_id}", json={"status": "closed"}, headers=viewer)
    assert patch.status_code == 403


async def test_reassigning_needs_bugs_assign_even_for_editors(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await new_org(pg_session_factory)
    dev_id = await new_member(pg_session_factory, org, "developer")
    dev = as_user(dev_id, org)
    manager = as_user(await new_member(pg_session_factory, org, "manager"), org)
    bug_id = await _file_bug(client, dev)

    denied = await client.patch(f"{BUGS}/{bug_id}", json={"assigneeId": str(dev_id)}, headers=dev)
    allowed = await client.patch(
        f"{BUGS}/{bug_id}", json={"assigneeId": str(dev_id)}, headers=manager
    )
    resolved = await client.patch(f"{BUGS}/{bug_id}", json={"status": "resolved"}, headers=dev)

    assert denied.status_code == 403
    assert allowed.status_code == 200
    assert allowed.json()["assigneeId"] == str(dev_id)
    assert resolved.status_code == 200


@pytest.mark.parametrize(
    "body",
    [
        {"title": "x", "severity": "urgent"},
        {"title": "x" * 501},
        {"title": "x", "bugType": "staging"},
        {"title": "x", "featureId": str(uuid.uuid4()), "bugType": "testing"},
        {},
    ],
    ids=["bad-severity", "title-too-long", "bad-type", "testing-with-feature", "no-title"],
)
async def test_invalid_bug_bodies_are_rejected(
    client: AsyncClient, pg_session_factory: Factory, body: dict[str, object]
) -> None:
    org = await new_org(pg_session_factory)
    headers = as_user(await new_member(pg_session_factory, org, "developer"), org)
    assert (await client.post(BUGS, json=body, headers=headers)).status_code == 422


async def test_an_unknown_status_value_is_rejected(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await new_org(pg_session_factory)
    headers = as_user(await new_member(pg_session_factory, org, "manager"), org)
    bug_id = await _file_bug(client, headers)
    resp = await client.patch(f"{BUGS}/{bug_id}", json={"status": "done"}, headers=headers)
    assert resp.status_code == 422
