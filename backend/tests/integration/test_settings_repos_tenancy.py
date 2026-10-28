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

"""Another org's tracked repos, org record and MCP tokens are out of reach.

Each test makes two orgs, gives the first a row, and has the second
org's owner (who holds every permission in *their* org) go after it by
id or path. The answer is always "not found", and the row is unchanged.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.api.v1 import settings_repos
from app.models.tracked_repository import RepoStatus, TrackedRepository
from app.models.user_mcp_token import UserMCPToken
from tests.integration.settings_support import Factory, add_tracked_repo, make_org

pytestmark = pytest.mark.integration

REPOS = "/api/v1/settings/repos"


@pytest.fixture(autouse=True)
def cache_drops(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Keys the remove endpoint drops from Redis, recorded instead of sent."""
    dropped: list[str] = []

    async def _drop(key: str) -> None:
        dropped.append(key)

    monkeypatch.setattr(settings_repos, "delete_key", _drop)
    return dropped


async def _repo(factory: Factory, repo_id: uuid.UUID) -> TrackedRepository:
    async with factory() as db:
        row = await db.get(TrackedRepository, repo_id)
        assert row is not None
        return row


async def test_another_orgs_repo_cannot_be_changed_or_read(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    owner_org, other = await make_org(pg_session_factory), await make_org(pg_session_factory)
    path = f"/srv/{uuid.uuid4().hex}/billing"
    repo_id = await add_tracked_repo(pg_session_factory, owner_org.id, path)
    headers = other.owner.headers

    attempts = [
        await client.get(f"{REPOS}/{repo_id}/branches", headers=headers),
        await client.patch(
            f"{REPOS}/{repo_id}/branches", headers=headers, json={"mainBranch": "hijack"}
        ),
        await client.patch(
            f"{REPOS}/{repo_id}/status", headers=headers, json={"status": "ignored"}
        ),
        await client.post(f"{REPOS}/{repo_id}/classify", headers=headers),
        await client.post(f"{REPOS}/{repo_id}/extract-routes", headers=headers),
        await client.request("DELETE", REPOS, headers=headers, json={"path": path}),
    ]

    assert [r.status_code for r in attempts] == [404] * len(attempts)
    row = await _repo(pg_session_factory, repo_id)
    assert (row.main_branch, row.status, row.repo_layer) == ("main", RepoStatus.ACTIVE, None)
    listed = await client.get(REPOS, headers=headers)
    assert all(r["path"] != path for r in listed.json())


async def test_the_owning_org_still_reaches_its_repo(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await make_org(pg_session_factory)
    path = f"/srv/{uuid.uuid4().hex}/billing"
    repo_id = await add_tracked_repo(pg_session_factory, org.id, path)

    patched = await client.patch(
        f"{REPOS}/{repo_id}/branches",
        headers=org.owner.headers,
        json={"mainBranch": "trunk", "uatBranch": "uat"},
    )
    cleared = await client.patch(
        f"{REPOS}/{repo_id}/branches", headers=org.owner.headers, json={"uatBranch": ""}
    )
    bad_status = await client.patch(
        f"{REPOS}/{repo_id}/status", headers=org.owner.headers, json={"status": "removed"}
    )

    assert patched.status_code == cleared.status_code == 200, patched.text
    assert bad_status.status_code == 400
    row = await _repo(pg_session_factory, repo_id)
    assert (row.main_branch, row.uat_branch, row.status) == ("trunk", None, RepoStatus.ACTIVE)


async def test_removing_a_repo_hides_it_from_the_list_but_keeps_the_row(
    client: AsyncClient, pg_session_factory: Factory, cache_drops: list[str]
) -> None:
    org = await make_org(pg_session_factory)
    path = f"/srv/{uuid.uuid4().hex}/billing"
    repo_id = await add_tracked_repo(pg_session_factory, org.id, path)

    removed = await client.request("DELETE", REPOS, headers=org.owner.headers, json={"path": path})
    again = await client.request("DELETE", REPOS, headers=org.owner.headers, json={"path": "/x"})

    assert removed.json() == {"removed": path, "deactivated": 0}
    assert cache_drops == [settings_repos.INSTALLABLE_CACHE_KEY_TEMPLATE.format(org_id=org.id)]
    assert again.status_code == 404
    assert (await _repo(pg_session_factory, repo_id)).status == RepoStatus.REMOVED
    listed = await client.get(REPOS, headers=org.owner.headers)
    assert listed.json() == []


async def test_another_orgs_record_reads_as_not_found(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    mine, theirs = await make_org(pg_session_factory), await make_org(pg_session_factory)

    own = await client.get(f"/api/v1/organizations/{mine.id}", headers=mine.developer.headers)
    other = await client.get(f"/api/v1/organizations/{theirs.id}", headers=mine.owner.headers)
    listed = await client.get("/api/v1/organizations/", headers=mine.owner.headers)

    assert own.status_code == 200 and own.json()["slug"] == mine.slug
    assert other.status_code == 404
    assert [o["id"] for o in listed.json()] == [str(mine.id)]


async def test_only_an_owner_creates_an_org_and_slugs_are_unique(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    org = await make_org(pg_session_factory)
    slug = f"new-{uuid.uuid4().hex[:8]}"

    by_developer = await client.post(
        "/api/v1/organizations/", headers=org.developer.headers, json={"name": "X", "slug": slug}
    )
    taken = await client.post(
        "/api/v1/organizations/", headers=org.owner.headers, json={"name": "X", "slug": org.slug}
    )

    assert by_developer.status_code == 403
    assert taken.status_code == 409


async def test_mcp_tokens_of_another_org_are_neither_listed_nor_revocable(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    mine, theirs = await make_org(pg_session_factory), await make_org(pg_session_factory)
    async with pg_session_factory() as db:
        token = UserMCPToken(
            user_id=theirs.developer.user_id,
            org_id=theirs.id,
            name="laptop",
            token_hash="hash",
            token_prefix="bo_abc",
        )
        db.add(token)
        await db.commit()
        token_id = token.id

    listed = await client.get("/api/v1/settings/mcp-tokens", headers=mine.owner.headers)
    revoked = await client.delete(
        f"/api/v1/settings/mcp-tokens/{token_id}", headers=mine.owner.headers
    )
    by_developer = await client.get(
        "/api/v1/settings/mcp-tokens", headers=theirs.developer.headers
    )
    theirs_listed = await client.get("/api/v1/settings/mcp-tokens", headers=theirs.owner.headers)

    assert listed.json() == []
    assert revoked.status_code == 404
    assert by_developer.status_code == 403
    assert [t["id"] for t in theirs_listed.json()] == [str(token_id)]
    assert "hash" not in theirs_listed.json()[0].values()
