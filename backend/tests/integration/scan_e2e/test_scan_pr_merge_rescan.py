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
"""

from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.repositories.scan import ScanRepository
from app.repositories.webhook_log import WebhookLogRepository
from app.services.scan.pr_merge_update import handle_pr_merge_delivery
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.github_payloads import pull_request_event
from tests.fakes.seed import WEBHOOK_SECRET
from tests.fakes.signing import signed_github_webhook
from tests.integration.scan_e2e.merge_support import (
    TAX,
    WEBHOOK_URL,
    Merged,
    deliver,
    narrow_prompts,
    scanned_on_github,
)
from tests.integration.scan_e2e.scan_support import (
    SYNTHESIS_MARKER,
    Factory,
    active_last_seen,
    cache_counts,
    prompt_clusters,
    tracked_repo,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]

NEW_TAX = "RATE = 0.25\n\n\ndef apply_tax(amount):\n    return round(amount * 1.25, 2)\n"


def _delivery(name: str) -> str:
    return f"{name}-{uuid.uuid4().hex[:8]}"


async def _latest_scan_id(factory: Factory, s: Merged) -> uuid.UUID | None:
    async with factory() as db:
        latest = await ScanRepository(db, org_id=s.org_id).get_latest()
        return latest.id if latest else None


async def test_merged_pr_reindexes_and_reconciles_only_what_changed(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await scanned_on_github(client, app_sessions, mcp_claude, fake_github, shop_repo)
    before = await active_last_seen(app_sessions, s.org_id, s.repo_id)
    head = shop_repo.commit({TAX: NEW_TAX}, "Raise the tax rate")
    fake_github.pr_files[(s.full_name, 7)] = [TAX]
    payload = pull_request_event(s.full_name, 7, merge_commit_sha=head, base_sha=s.base_sha)
    delivery = _delivery("merge-7")

    assert await deliver(client, payload, delivery) == 200
    async with app_sessions() as db:
        row = await WebhookLogRepository(db).find_by_delivery_id(delivery)
    assert row is not None and row.payload is not None
    assert row.payload["head_sha"] == head
    await handle_pr_merge_delivery(delivery)

    (narrow,) = narrow_prompts(mcp_claude)
    full_prompt = mcp_claude.runs[0].prompt
    assert "billing/tax.py" in narrow
    assert len(prompt_clusters(narrow)) < len(prompt_clusters(full_prompt))
    assert (await cache_counts(app_sessions, s.org_id, s.repo_id, head))[0] > 0
    assert (await tracked_repo(app_sessions, s.org_id, s.repo_id)).head_sha == head
    (write,) = mcp_claude.tool_calls(SYNTHESIS_MARKER)[2:]
    assert write.status_code == 200
    after = await active_last_seen(app_sessions, s.org_id, s.repo_id)
    assert after.keys() == before.keys()
    assert sorted(str(sha) for sha in after.values()) == sorted([head, s.base_sha])
    assert (f"/repos/{s.full_name}/pulls/7/files", 200) in fake_github.responses
    assert await _latest_scan_id(app_sessions, s) == s.scan_id


async def test_pr_that_touches_no_code_cluster_skips_the_agent(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await scanned_on_github(client, app_sessions, mcp_claude, fake_github, shop_repo)
    before = await active_last_seen(app_sessions, s.org_id, s.repo_id)
    head = shop_repo.commit({"README.md": "# shop-api\n\nNow with docs.\n"}, "Docs")
    fake_github.pr_files[(s.full_name, 8)] = ["README.md"]
    payload = pull_request_event(s.full_name, 8, merge_commit_sha=head, base_sha=s.base_sha)
    delivery = _delivery("merge-8")

    assert await deliver(client, payload, delivery) == 200
    await handle_pr_merge_delivery(delivery)

    assert narrow_prompts(mcp_claude) == []
    assert len(mcp_claude.runs) == 1
    assert (await tracked_repo(app_sessions, s.org_id, s.repo_id)).head_sha == head
    assert await active_last_seen(app_sessions, s.org_id, s.repo_id) == before
    assert await _latest_scan_id(app_sessions, s) == s.scan_id


async def test_forged_signature_is_refused_and_records_nothing(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await scanned_on_github(client, app_sessions, mcp_claude, fake_github, shop_repo)
    payload = pull_request_event(s.full_name, 9, merge_commit_sha="9" * 40, base_sha=s.base_sha)
    delivery = _delivery("forged-9")

    assert await deliver(client, payload, delivery, secret="not-the-secret") == 401

    async with app_sessions() as db:
        assert await WebhookLogRepository(db).find_by_delivery_id(delivery) is None


async def test_redelivered_merge_is_a_duplicate_and_synthesises_once(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await scanned_on_github(client, app_sessions, mcp_claude, fake_github, shop_repo)
    head = shop_repo.commit({TAX: NEW_TAX}, "Raise the tax rate")
    fake_github.pr_files[(s.full_name, 11)] = [TAX]
    payload = pull_request_event(s.full_name, 11, merge_commit_sha=head, base_sha=s.base_sha)
    delivery = _delivery("merge-11")
    assert await deliver(client, payload, delivery) == 200
    await handle_pr_merge_delivery(delivery)
    body, headers = signed_github_webhook(WEBHOOK_SECRET, "pull_request", payload, delivery)

    again = await client.post(WEBHOOK_URL, content=body, headers=headers)

    assert again.json() == {"status": "duplicate"}
    assert len(narrow_prompts(mcp_claude)) == 1


async def test_merge_into_develop_is_recorded_but_never_synthesised(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    fake_github: FakeGitHub,
    shop_repo: LocalGitRepo,
    data_dir: Path,
) -> None:
    s = await scanned_on_github(client, app_sessions, mcp_claude, fake_github, shop_repo)
    to_develop = pull_request_event(s.full_name, 10, base="develop", base_sha=s.base_sha)
    delivery = _delivery("dev-10")

    assert await deliver(client, to_develop, delivery) == 200
    async with app_sessions() as db:
        row = await WebhookLogRepository(db).find_by_delivery_id(delivery)
    assert row is not None and row.payload is None
    await handle_pr_merge_delivery(delivery)

    assert narrow_prompts(mcp_claude) == []
    assert (await tracked_repo(app_sessions, s.org_id, s.repo_id)).head_sha == s.base_sha
