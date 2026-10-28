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

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from httpx import AsyncClient

from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.jobs import JobState
from app.services import github_app_auth
from app.services.job_queue import JOB_REPO_BULK_ONBOARD
from app.services.job_repo_bulk_clone import handle_bulk_onboard_job
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import Factory, SeededOrg, auth_headers, seed_org
from tests.integration.external_flows.bulk_onboard_support import (
    CloneRedirects,
    ScanKickoffs,
    onboard_item,
)
from tests.integration.external_flows.github_support import BULK_ONBOARD, set_installation
from tests.integration.external_flows.jobs_support import InlineJobs

pytestmark = pytest.mark.integration
RepoFactory = Callable[..., LocalGitRepo]


@pytest.fixture
def onboarding(
    inline_jobs: InlineJobs, app_sessions: Factory, data_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> ScanKickoffs:
    """The real bulk-onboard handler on the test database; the scan is recorded."""

    async def handler(job_id: str, payload: dict[str, Any]) -> None:
        await handle_bulk_onboard_job(job_id, payload, db_factory=app_sessions)

    inline_jobs.register(JOB_REPO_BULK_ONBOARD, handler)
    return ScanKickoffs().install(monkeypatch)


async def _start(client: AsyncClient, org: SeededOrg, *items: dict[str, str]) -> str:
    resp = await client.post(
        BULK_ONBOARD, json={"items": list(items)}, headers=auth_headers(org.owner_id, org.org_id)
    )
    assert resp.status_code == 202, resp.text
    return str(resp.json()["jobId"])


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
    shop, billing = git_repo_factory("shop-api"), git_repo_factory("billing")
    gh.add_repo("acme/shop-api", "main", "develop")
    gh.add_repo("acme/billing")
    org = await seed_org(app_sessions, github=gh)

    job_id = await _start(
        client, org, onboard_item("acme/shop-api", develop="develop"), onboard_item("acme/billing")
    )
    token = gh.issued_tokens[0]
    redirects = CloneRedirects(monkeypatch)
    redirects.serve(token, "acme/shop-api", shop)
    redirects.serve(token, "acme/billing", billing)
    await inline_jobs.run_all()

    status = inline_jobs.status(job_id)
    assert status.state == JobState.COMPLETED
    assert status.result is not None
    assert sorted(status.result["succeeded"]) == ["acme/billing", "acme/shop-api"]
    assert status.result["failed"] == []
    assert token not in str(status.result)
    async with app_sessions() as db:
        rows = await TrackedRepoRepository(db, org_id=org.org_id).list_all_ordered_by_name()
    by_name = {r.github_repo_full_name: r for r in rows}
    shop_row = by_name["acme/shop-api"]
    assert (shop_row.main_branch, shop_row.develop_branch) == ("main", "develop")
    assert Path(shop_row.path) == (data_dir / "repos" / org.slug / "shop-api").resolve()
    assert (Path(shop_row.path) / "README.md").read_text().startswith("# shop-api")
    (scanned,) = onboarding.calls
    assert sorted(scanned) == sorted(r.id for r in rows)


async def test_one_failed_clone_leaves_the_other_repo_onboarded_and_hides_the_token(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    git_repo_factory: RepoFactory,
    inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shop = git_repo_factory("shop-api")
    gh.add_repo("acme/shop-api")
    gh.add_repo("acme/ghost")
    org = await seed_org(app_sessions, github=gh)

    job_id = await _start(client, org, onboard_item("acme/shop-api"), onboard_item("acme/ghost"))
    token = gh.issued_tokens[0]
    CloneRedirects(monkeypatch).serve(token, "acme/shop-api", shop)
    await inline_jobs.run_all()

    result = inline_jobs.status(job_id).result
    assert result is not None
    assert result["succeeded"] == ["acme/shop-api"]
    (failure,) = result["failed"]
    assert failure["full_name"] == "acme/ghost"
    assert failure["error"] and token not in failure["error"]
    async with app_sessions() as db:
        rows = await TrackedRepoRepository(db, org_id=org.org_id).list_all_ordered_by_name()
    assert [r.github_repo_full_name for r in rows] == ["acme/shop-api"]
    assert onboarding.calls == [[rows[0].id]]


async def test_repos_outside_the_installation_are_refused_before_any_job(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
) -> None:  # fmt: skip
    gh.add_repo("acme/shop-api")
    org = await seed_org(app_sessions, github=gh)

    resp = await client.post(
        BULK_ONBOARD,
        json={"items": [onboard_item("acme/shop-api"), onboard_item("other/secret")]},
        headers=auth_headers(org.owner_id, org.org_id),
    )

    assert resp.status_code == 400
    assert "other/secret" in resp.json()["detail"]
    assert "acme/shop-api" not in resp.json()["detail"]
    assert inline_jobs.queued(JOB_REPO_BULK_ONBOARD) == 0


async def test_bulk_onboard_needs_the_app_installed(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
) -> None:  # fmt: skip
    gh.add_repo("acme/shop-api")
    org = await seed_org(app_sessions, github=gh)
    await set_installation(app_sessions, org.org_id, None)

    resp = await client.post(
        BULK_ONBOARD,
        json={"items": [onboard_item("acme/shop-api")]},
        headers=auth_headers(org.owner_id, org.org_id),
    )

    assert resp.status_code == 400
    assert inline_jobs.queued(JOB_REPO_BULK_ONBOARD) == 0
    assert gh.requests == []


async def test_a_revoked_installation_at_job_time_fails_the_job_without_cloning(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    inline_jobs: InlineJobs,
    onboarding: ScanKickoffs,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gh.add_repo("acme/shop-api")
    org = await seed_org(app_sessions, github=gh)
    job_id = await _start(client, org, onboard_item("acme/shop-api"))
    # The cached token expires and GitHub now refuses the installation.
    monkeypatch.setattr(github_app_auth, "_token_cache", {})
    gh.fail("POST", r"/access_tokens$", 404)

    await inline_jobs.run_all()

    status = inline_jobs.status(job_id)
    assert status.state == JobState.FAILED
    assert status.error == "GitHub App installation is not ready for this organization."
    async with app_sessions() as db:
        assert await TrackedRepoRepository(db, org_id=org.org_id).list_all_ordered_by_name() == []
    assert onboarding.calls == []
