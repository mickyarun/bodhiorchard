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

"""Release detection end to end: a BUD's merge commit found by walking a release PR on GitHub.

A BUD branch PR merges into ``develop`` (its merge SHA is recorded), then a
release PR with no BUD in its name merges ``develop`` into ``main``. The
webhook asks GitHub for the release PR's commits, through the installation
token, and records ``merged_to_prod`` on every BUD whose merge SHA is there.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.pull_request import PRState
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.github_payloads import pull_request_event
from tests.fakes.seed import Factory, SeededOrg, seed_org, seed_repo
from tests.integration.external_flows.github_support import bearer_tokens, unique_name
from tests.integration.external_flows.webhook_support import (
    add_bud,
    deliver,
    pull_request,
    timeline_details,
)

pytestmark = pytest.mark.integration
BUD_SHA = "b" * 40
OTHER_SHA = "c" * 40
RELEASE_PR = 90


async def _ship_bud_to_develop(
    client: AsyncClient, factory: Factory, org: SeededOrg, full_name: str
) -> uuid.UUID:
    """Open and merge ``bud-NNN/work`` into develop; return the BUD id."""
    bud_id, number = await add_bud(factory, org.org_id, "Refund to wallet")
    branch = f"bud-{number:03d}/refund-wallet"
    opened = pull_request_event(full_name, 11, action="opened", merged=False, base="develop",
                                head=branch)  # fmt: skip
    merged = pull_request_event(full_name, 11, base="develop", head=branch,
                                merge_commit_sha=BUD_SHA)  # fmt: skip
    assert (await deliver(client, "pull_request", opened)).status_code == 200
    assert (await deliver(client, "pull_request", merged)).status_code == 200
    return bud_id


async def _release(client: AsyncClient, full_name: str, delivery_id: str | None = None) -> None:
    """Open and merge the develop -> main release PR."""
    title = "Release 2026.10"
    opened = pull_request_event(
        full_name, RELEASE_PR, action="opened", merged=False, head="develop", title=title
    )
    merged = pull_request_event(
        full_name, RELEASE_PR, head="develop", title=title, merge_commit_sha="d" * 40
    )
    await deliver(client, "pull_request", opened)
    resp = await deliver(client, "pull_request", merged, delivery_id=delivery_id)
    assert resp.status_code == 200


async def _tracked_org(
    factory: Factory, gh: FakeGitHub, repo: LocalGitRepo
) -> tuple[SeededOrg, str]:
    full_name = f"acme/{unique_name('shop')}"
    gh.add_repo(full_name, "main", "develop")
    org = await seed_org(factory, github=gh)
    await seed_repo(factory, org.org_id, repo, full_name=full_name)
    return org, full_name


async def test_a_release_pr_walk_records_prod_on_the_bud_whose_commit_it_carries(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, git_repo: LocalGitRepo
) -> None:
    org, full_name = await _tracked_org(app_sessions, gh, git_repo)
    bud_id = await _ship_bud_to_develop(client, app_sessions, org, full_name)
    gh.pr_commits[(full_name, RELEASE_PR)] = [OTHER_SHA, BUD_SHA]

    await _release(client, full_name)

    (prod,) = await timeline_details(app_sessions, org.org_id, bud_id, "merged_to_prod")
    assert prod["release_pr_number"] == RELEASE_PR
    assert prod["release_pr_title"] == "Release 2026.10"
    assert prod["matched_commits"] == [{"sha": BUD_SHA, "message": ""}]
    assert len(await timeline_details(app_sessions, org.org_id, bud_id, "merged_to_develop")) == 1
    walk = bearer_tokens(gh, f"/pulls/{RELEASE_PR}/commits")
    assert walk == [gh.issued_tokens[0]]
    release = await pull_request(app_sessions, org.org_id, 10_000 + RELEASE_PR)
    assert (release.state, release.bud_id) == (PRState.MERGED, None)


async def test_a_release_without_any_bud_commit_records_nothing(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, git_repo: LocalGitRepo
) -> None:
    org, full_name = await _tracked_org(app_sessions, gh, git_repo)
    bud_id = await _ship_bud_to_develop(client, app_sessions, org, full_name)
    gh.pr_commits[(full_name, RELEASE_PR)] = [OTHER_SHA]

    await _release(client, full_name)

    assert await timeline_details(app_sessions, org.org_id, bud_id, "merged_to_prod") == []
    assert len(bearer_tokens(gh, f"/pulls/{RELEASE_PR}/commits")) == 1


@pytest.mark.parametrize("failure", ["token_refused", "commits_unavailable"])
async def test_github_failures_during_the_walk_still_record_the_merge(
    failure: str,
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    git_repo: LocalGitRepo,
) -> None:
    org, full_name = await _tracked_org(app_sessions, gh, git_repo)
    bud_id = await _ship_bud_to_develop(client, app_sessions, org, full_name)
    gh.pr_commits[(full_name, RELEASE_PR)] = [BUD_SHA]
    if failure == "token_refused":
        gh.fail("POST", r"/access_tokens$", 401)
    else:
        gh.fail("GET", rf"/pulls/{RELEASE_PR}/commits$", 500)

    await _release(client, full_name)

    assert await timeline_details(app_sessions, org.org_id, bud_id, "merged_to_prod") == []
    release = await pull_request(app_sessions, org.org_id, 10_000 + RELEASE_PR)
    assert release.state == PRState.MERGED


async def test_a_redelivered_release_merge_does_not_record_prod_twice(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, git_repo: LocalGitRepo
) -> None:
    org, full_name = await _tracked_org(app_sessions, gh, git_repo)
    bud_id = await _ship_bud_to_develop(client, app_sessions, org, full_name)
    gh.pr_commits[(full_name, RELEASE_PR)] = [BUD_SHA]

    await _release(client, full_name)
    # GitHub sends the same merge again under a fresh delivery id (a manual redeliver).
    merged = pull_request_event(full_name, RELEASE_PR, head="develop", title="Release 2026.10",
                                merge_commit_sha="d" * 40)  # fmt: skip
    assert (await deliver(client, "pull_request", merged)).status_code == 200

    assert len(await timeline_details(app_sessions, org.org_id, bud_id, "merged_to_prod")) == 1
    assert len(bearer_tokens(gh, f"/pulls/{RELEASE_PR}/commits")) == 2
