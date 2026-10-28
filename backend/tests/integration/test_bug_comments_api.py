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

"""The bug comment thread: posting, author-only edits, tombstones and org walls."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from httpx import AsyncClient

from app.services import bug_linker
from tests.integration.scan_features_bugs_support import (
    Factory,
    as_user,
    new_member,
    new_org,
    vec,
)

pytestmark = pytest.mark.integration

BUGS = "/api/v1/bugs"


@pytest.fixture(autouse=True)
def _fake_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the real embedding model out of bug creation."""

    async def _embed(text: str) -> list[float]:
        return vec(0, 1)

    monkeypatch.setattr(bug_linker, "embedding_service", SimpleNamespace(embed=_embed))


async def _thread(
    client: AsyncClient, factory: Factory
) -> tuple[uuid.UUID, str, dict[str, str], dict[str, str]]:
    """An org with one bug; returns (org, bug id, developer headers, designer headers)."""
    org = await new_org(factory)
    dev = as_user(await new_member(factory, org, "developer"), org)
    designer = as_user(await new_member(factory, org, "designer"), org)
    resp = await client.post(BUGS, json={"title": "Broken"}, headers=dev)
    return org, str(resp.json()["id"]), dev, designer


async def _comment(client: AsyncClient, bug: str, headers: dict[str, str], text: str) -> str:
    resp = await client.post(f"{BUGS}/{bug}/comments", json={"body": text}, headers=headers)
    assert resp.status_code == 201, resp.text
    return str(resp.json()["id"])


async def test_comments_are_listed_oldest_first_with_unicode_intact(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, bug, dev, designer = await _thread(client, pg_session_factory)
    await _comment(client, bug, dev, "First: repro on Safari")
    await _comment(client, bug, designer, "Second: ça marche pas 🙃 — 再現しました")

    listed = (await client.get(f"{BUGS}/{bug}/comments", headers=dev)).json()
    detail = (await client.get(f"{BUGS}/{bug}", headers=dev)).json()

    assert [c["body"] for c in listed["items"]] == [
        "First: repro on Safari",
        "Second: ça marche pas 🙃 — 再現しました",
    ]
    assert listed["total"] == 2
    assert detail["commentCount"] == 2


async def test_the_author_edits_and_deletes_leaving_a_tombstone(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, bug, dev, _ = await _thread(client, pg_session_factory)
    cid = await _comment(client, bug, dev, "typo")
    url = f"{BUGS}/{bug}/comments/{cid}"

    edited = await client.patch(url, json={"body": "fixed"}, headers=dev)
    deleted = await client.delete(url, headers=dev)
    again = await client.delete(url, headers=dev)
    edit_after = await client.patch(url, json={"body": "revive"}, headers=dev)
    detail = (await client.get(f"{BUGS}/{bug}", headers=dev)).json()

    assert edited.json()["body"] == "fixed" and edited.json()["editedAt"] is not None
    assert deleted.json()["body"] == "" and deleted.json()["deletedAt"] is not None
    assert again.status_code == 200
    assert again.json()["deletedAt"] == deleted.json()["deletedAt"]
    assert edit_after.status_code == 409
    assert detail["commentCount"] == 0


async def test_someone_elses_comment_needs_edit_rights(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, bug, dev, designer = await _thread(client, pg_session_factory)
    manager = as_user(await new_member(pg_session_factory, org, "manager"), org)
    cid = await _comment(client, bug, designer, "mine")
    url = f"{BUGS}/{bug}/comments/{cid}"

    other_designer = as_user(await new_member(pg_session_factory, org, "designer"), org)
    denied = await client.patch(url, json={"body": "hijack"}, headers=other_designer)
    denied_delete = await client.delete(url, headers=other_designer)
    moderated = await client.patch(url, json={"body": "moderated"}, headers=manager)
    by_dev = await client.patch(url, json={"body": "dev edit"}, headers=dev)

    assert denied.status_code == 403 and denied_delete.status_code == 403
    assert moderated.status_code == 200
    assert by_dev.status_code == 200 and by_dev.json()["body"] == "dev edit"


async def test_a_viewer_reads_the_thread_but_cannot_post(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org, bug, dev, _ = await _thread(client, pg_session_factory)
    viewer = as_user(await new_member(pg_session_factory, org, "viewer"), org)
    await _comment(client, bug, dev, "hello")

    listed = await client.get(f"{BUGS}/{bug}/comments", headers=viewer)
    posted = await client.post(f"{BUGS}/{bug}/comments", json={"body": "hi"}, headers=viewer)

    assert listed.status_code == 200 and listed.json()["total"] == 1
    assert posted.status_code == 403


async def test_another_orgs_thread_is_not_found(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, bug, dev, _ = await _thread(client, pg_session_factory)
    cid = await _comment(client, bug, dev, "private")
    _, _, outsider, _ = await _thread(client, pg_session_factory)
    url = f"{BUGS}/{bug}/comments"

    assert (await client.get(url, headers=outsider)).status_code == 404
    assert (await client.post(url, json={"body": "x"}, headers=outsider)).status_code == 404
    edit = await client.patch(f"{url}/{cid}", json={"body": "x"}, headers=outsider)
    assert edit.status_code == 404
    assert (await client.delete(f"{url}/{cid}", headers=outsider)).status_code == 404
    still = (await client.get(url, headers=dev)).json()["items"]
    assert [c["body"] for c in still] == ["private"]


async def test_a_comment_cannot_be_reached_through_another_bug(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, bug, dev, _ = await _thread(client, pg_session_factory)
    other_bug = (await client.post(BUGS, json={"title": "Other"}, headers=dev)).json()["id"]
    cid = await _comment(client, bug, dev, "on the first bug")

    resp = await client.patch(
        f"{BUGS}/{other_bug}/comments/{cid}", json={"body": "moved"}, headers=dev
    )

    assert resp.status_code == 404


@pytest.mark.parametrize("text", ["", "x" * 10001], ids=["empty", "over-10000"])
async def test_comment_bodies_must_be_1_to_10000_characters(
    client: AsyncClient, pg_session_factory: Factory, text: str
) -> None:
    _, bug, dev, _ = await _thread(client, pg_session_factory)
    resp = await client.post(f"{BUGS}/{bug}/comments", json={"body": text}, headers=dev)
    assert resp.status_code == 422


async def test_a_comment_of_exactly_10000_characters_is_accepted(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    _, bug, dev, _ = await _thread(client, pg_session_factory)
    resp = await client.post(f"{BUGS}/{bug}/comments", json={"body": "y" * 10000}, headers=dev)
    assert resp.status_code == 201
    assert len(resp.json()["body"]) == 10000
