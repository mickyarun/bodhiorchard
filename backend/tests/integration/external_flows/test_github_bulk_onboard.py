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

"""Bulk onboarding of App-visible repos: the 202 route, then the real clone job."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.models.tracked_repository import TrackedRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.jobs import JobState
from app.services import github_app_auth
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, seed_org
from tests.integration.external_flows.bulk_onboard_support import (
    CloneRedirects,
    ScanKickoffs,
    onboard_item,
    origin_url,
    start_onboard,
)
from tests.integration.external_flows.github_support import unique_name
from tests.integration.external_flows.jobs_support import InlineJobs

pytestmark = pytest.mark.integration
RepoFactory = Callable[..., LocalGitRepo]


async def _tracked(factory: Factory, org_id: uuid.UUID) -> dict[str | None, TrackedRepository]:
    """The org's tracked repos by GitHub full name."""
    async with factory() as db:
        rows = await TrackedRepoRepository(db, org_id=org_id).list_all_ordered_by_name()
    return {r.github_repo_full_name: r for r in rows}


async def test_two_repos_are_cloned_registered_and_handed_to_one_scan(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    git_repo_factory: RepoFactory,
    inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
    monkeypatch: pytest.MonkeyPatch,
    data_dir: Path,
) -> None:
    shop_name = unique_name("shop")
    shop, billing = f"acme/{shop_name}", f"acme/{unique_name('billing')}"
    gh.add_repo(shop, "main", "develop")
    gh.add_repo(billing)
    org = await seed_org(app_sessions, github=gh)

    job_id = await start_onboard(
        client, org, onboard_item(shop, develop="develop"), onboard_item(billing)
    )
    token = gh.issued_tokens[0]
    redirects = CloneRedirects(monkeypatch)
    redirects.serve(token, shop, git_repo_factory("shop-api"))
    redirects.serve(token, billing, git_repo_factory("billing"))
    await inline_jobs.run_all()

    status = inline_jobs.status(job_id)
    assert status.state == JobState.COMPLETED
    assert status.result is not None
    assert sorted(status.result["succeeded"]) == sorted([shop, billing])
    assert status.result["failed"] == []
    assert token not in str(status.result)
    assert len(gh.issued_tokens) == 1  # one installation token for the whole job
    rows = await _tracked(app_sessions, org.org_id)
    shop_row = rows[shop]
    assert (shop_row.main_branch, shop_row.develop_branch) == ("main", "develop")
    clone = Path(shop_row.path)
    assert clone == (data_dir / "repos" / org.slug / shop_name).resolve()
    assert (clone / "README.md").read_text().startswith("# shop-api")
    (scanned,) = onboarding.calls
    assert sorted(scanned) == sorted(r.id for r in rows.values())


async def test_one_failed_clone_leaves_the_other_repo_onboarded_and_hides_the_token(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    git_repo_factory: RepoFactory,
    inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop, ghost = f"acme/{unique_name('shop')}", f"acme/{unique_name('ghost')}"
    gh.add_repo(shop)
    gh.add_repo(ghost)
    org = await seed_org(app_sessions, github=gh)

    job_id = await start_onboard(client, org, onboard_item(shop), onboard_item(ghost))
    token = gh.issued_tokens[0]
    CloneRedirects(monkeypatch).serve(token, shop, git_repo_factory("shop-api"))
    await inline_jobs.run_all()

    result = inline_jobs.status(job_id).result
    assert result is not None
    assert result["succeeded"] == [shop]
    (failure,) = result["failed"]
    assert failure["full_name"] == ghost
    assert failure["error"] and token not in failure["error"]
    assert len(gh.issued_tokens) == 1
    rows = await _tracked(app_sessions, org.org_id)
    assert list(rows) == [shop]
    assert onboarding.calls == [[rows[shop].id]]


@pytest.mark.xfail(
    strict=True,
    reason="open question in the release test plan: the cloner's docstring says the token "
    "is never written to disk, but it stays in the clone's .git/config",
)
async def test_the_clone_does_not_keep_the_installation_token_on_disk(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    git_repo_factory: RepoFactory,
    inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop = f"acme/{unique_name('shop')}"
    gh.add_repo(shop)
    org = await seed_org(app_sessions, github=gh)
    await start_onboard(client, org, onboard_item(shop))
    token = gh.issued_tokens[0]
    CloneRedirects(monkeypatch).serve(token, shop, git_repo_factory("shop-api"))
    await inline_jobs.run_all()

    row = (await _tracked(app_sessions, org.org_id))[shop]

    assert token not in origin_url(row.path)


async def test_a_revoked_installation_at_job_time_fails_the_job_without_cloning(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop = f"acme/{unique_name('shop')}"
    gh.add_repo(shop)
    org = await seed_org(app_sessions, github=gh)
    job_id = await start_onboard(client, org, onboard_item(shop))
    # The cached token expires and GitHub now refuses the installation.
    monkeypatch.setattr(github_app_auth, "_token_cache", {})
    gh.fail("POST", r"/access_tokens$", 404)

    await inline_jobs.run_all()

    status = inline_jobs.status(job_id)
    assert status.state == JobState.FAILED
    assert status.error == "GitHub App installation is not ready for this organization."
    assert gh.faults.faults == []
    assert await _tracked(app_sessions, org.org_id) == {}
    assert onboarding.calls == []
