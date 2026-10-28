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

"""Rescans driven by a merged pull request, from the signed webhook to the features.

GitHub delivers the merge, the route records a replay row, and the PR-merge
consumer (called here directly, since Redis is off) fetches the PR's files
from the fake GitHub, re-indexes the merge commit and runs the narrow
synthesis agent over the affected clusters only.

The bare repository plays GitHub. Before an agent run the app points a
GitHub-App org's clone at ``https://github.com/...`` (with a fresh App
token), which the guard keeps git from reaching, so after the first scan the
test points ``origin`` back at the bare repository, as GitHub would answer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.repositories.webhook_log import WebhookLogRepository
from app.services.scan.pr_merge_update import handle_pr_merge_delivery
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo, git
from tests.fakes.github import FakeGitHub
from tests.fakes.github_payloads import pull_request_event
from tests.fakes.seed import WEBHOOK_SECRET, auth_headers, seed_org, seed_repo
from tests.fakes.signing import signed_github_webhook
from tests.integration.scan_e2e.scan_support import (
    NARROW_MARKER,
    SYNTHESIS_MARKER,
    Factory,
    active_feature_titles,
    active_last_seen,
    feature_params,
    start_scan_over_http,
    synthesis_writing,
    tracked_repo,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]

WEBHOOK_URL = "/api/v1/webhooks/github"
TAX = "shop/billing/tax.py"
NEW_TAX = "RATE = 0.25\n\n\ndef apply_tax(amount):\n    return round(amount * 1.25, 2)\n"


@dataclass(frozen=True)
class Scanned:
    """An org whose repo has had one full scan.

    Each test tracks its own GitHub name: the webhook finds the repo by name
    alone, so two orgs tracking one name would see each other's deliveries.
    """

    org_id: uuid.UUID
    repo_id: uuid.UUID
    base_sha: str
    full_name: str


async def _scanned(
    client: AsyncClient,
    factory: Factory,
    claude: FakeClaudeRunner,
    github: FakeGitHub,
    repo: LocalGitRepo,
) -> Scanned:
    full_name = f"acme/shop-{uuid.uuid4().hex[:8]}"
    github.add_repo(full_name)
    org = await seed_org(factory, github=github)
    repo_id = await seed_repo(factory, org.org_id, repo, full_name=full_name)
    narrow = ToolCall(SYNTHESIS_MARKER, lambda run: feature_params(run, 0, "Taxed"))
    claude.when(NARROW_MARKER, AgentScript.ok("Reconciled.", narrow))
    claude.when(SYNTHESIS_MARKER, synthesis_writing(2))
    await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)
    origin_url = git(repo.work, "remote", "get-url", "origin")
    assert origin_url.startswith("https://x-access-token:ghs_fake")
    assert origin_url.endswith(f"@github.com/{full_name}.git")
    git(repo.work, "remote", "set-url", "origin", str(repo.origin))
    return Scanned(org.org_id, repo_id, repo.head("main"), full_name)


async def _deliver(
    client: AsyncClient, payload: dict[str, object], delivery: str, secret: str = WEBHOOK_SECRET
) -> int:
    body, headers = signed_github_webhook(secret, "pull_request", payload, delivery)
    return (await client.post(WEBHOOK_URL, content=body, headers=headers)).status_code


def _narrow_runs(claude: FakeClaudeRunner) -> list[str]:
    return [run.prompt for run in claude.runs if NARROW_MARKER in run.prompt]


async def test_merged_pr_reindexes_and_reconciles_only_what_changed(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await _scanned(client, app_sessions, mcp_claude, fake_github, shop_repo)
    head = shop_repo.commit({TAX: NEW_TAX}, "Raise the tax rate")
    fake_github.pr_files[(s.full_name, 7)] = [TAX]
    payload = pull_request_event(s.full_name, 7, merge_commit_sha=head, base_sha=s.base_sha)

    assert await _deliver(client, payload, "d-merge-7") == 200
    async with app_sessions() as db:
        row = await WebhookLogRepository(db).find_by_delivery_id("d-merge-7")
    assert row is not None and row.payload is not None
    assert row.payload["head_sha"] == head
    await handle_pr_merge_delivery("d-merge-7")

    (narrow_prompt,) = _narrow_runs(mcp_claude)
    assert TAX.split("/", 1)[1] in narrow_prompt or TAX in narrow_prompt
    assert (await tracked_repo(app_sessions, s.org_id, s.repo_id)).head_sha == head
    (write,) = [
        c for c in mcp_claude.tool_calls(SYNTHESIS_MARKER) if c.params["name"].startswith("Taxed")
    ]
    assert write.status_code == 200
    seen = await active_last_seen(app_sessions, s.org_id, s.repo_id)
    assert len(seen) == 2, "the overlapping write must merge into a feature, not add one"
    assert head in seen.values()
    assert (f"/repos/{s.full_name}/pulls/7/files", 200) in fake_github.responses


async def test_pr_that_touches_no_code_cluster_skips_the_agent(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await _scanned(client, app_sessions, mcp_claude, fake_github, shop_repo)
    before = await active_feature_titles(app_sessions, s.org_id, s.repo_id)
    head = shop_repo.commit({"README.md": "# shop-api\n\nNow with docs.\n"}, "Docs")
    fake_github.pr_files[(s.full_name, 8)] = ["README.md"]
    payload = pull_request_event(s.full_name, 8, merge_commit_sha=head, base_sha=s.base_sha)

    assert await _deliver(client, payload, "d-merge-8") == 200
    await handle_pr_merge_delivery("d-merge-8")

    assert _narrow_runs(mcp_claude) == []
    assert len(mcp_claude.runs) == 1
    assert (await tracked_repo(app_sessions, s.org_id, s.repo_id)).head_sha == head
    assert await active_feature_titles(app_sessions, s.org_id, s.repo_id) == before


async def test_forged_signature_is_refused_and_records_nothing(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await _scanned(client, app_sessions, mcp_claude, fake_github, shop_repo)
    payload = pull_request_event(s.full_name, 9, merge_commit_sha="9" * 40, base_sha=s.base_sha)

    assert await _deliver(client, payload, "d-forged-9", secret="not-the-secret") == 401

    async with app_sessions() as db:
        assert await WebhookLogRepository(db).find_by_delivery_id("d-forged-9") is None
    assert len(mcp_claude.runs) == 1


async def test_merge_into_develop_and_redelivery_never_start_synthesis(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await _scanned(client, app_sessions, mcp_claude, fake_github, shop_repo)
    to_develop = pull_request_event(s.full_name, 10, base="develop", base_sha=s.base_sha)

    assert await _deliver(client, to_develop, "d-dev-10") == 200
    async with app_sessions() as db:
        row = await WebhookLogRepository(db).find_by_delivery_id("d-dev-10")
    assert row is not None and row.payload is None
    await handle_pr_merge_delivery("d-dev-10")
    body, headers = signed_github_webhook(WEBHOOK_SECRET, "pull_request", to_develop, "d-dev-10")
    again = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert again.json() == {"status": "duplicate"}
    assert _narrow_runs(mcp_claude) == []
    assert (await tracked_repo(app_sessions, s.org_id, s.repo_id)).head_sha == s.base_sha
