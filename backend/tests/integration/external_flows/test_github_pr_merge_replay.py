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

"""A merge into ``main``: the webhook's replay row, then the worker reading the PR's files.

The worker's stream consumer needs Redis, so the test hands the delivery id
straight to ``handle_pr_merge_delivery``, as the consumer would. Its
indexer and scan steps are recorded instead of run (the scan suite covers
them); the part under test is the replay row and the GitHub file listing
feeding the cluster diff.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from httpx import AsyncClient

from app.services.scan import pr_merge_update
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.github import FakeGitHub
from tests.fakes.github_payloads import pull_request_event
from tests.fakes.seed import Factory, seed_org, seed_repo
from tests.integration.external_flows.github_support import (
    bearer_tokens,
    set_installation,
    unique_name,
)
from tests.integration.external_flows.webhook_support import deliver, webhook_log

pytestmark = pytest.mark.integration


@dataclass
class Dispatch:
    """What the worker handed to the cluster diff and the scan trigger."""

    changed_paths: list[set[str]] = field(default_factory=list)
    scans: list[dict[str, Any]] = field(default_factory=list)

    async def find(self, db: Any, **kwargs: Any) -> None:
        """Record the PR's changed paths; report a cache miss."""
        self.changed_paths.append(set(kwargs["changed_paths"]))

    async def trigger(self, **kwargs: Any) -> None:
        """Record the full-scan fallback."""
        self.scans.append(kwargs)

    async def skip_backfill(self, **kwargs: Any) -> None:
        """The indexer run at the merge SHA is the scan suite's business."""


@pytest.fixture
def dispatch(monkeypatch: pytest.MonkeyPatch) -> Dispatch:
    """Record the worker's cluster diff and scan trigger."""
    recorder = Dispatch()
    monkeypatch.setattr(pr_merge_update, "_find_affected_clusters", recorder.find)
    monkeypatch.setattr(pr_merge_update, "_trigger_repo_scan", recorder.trigger)
    monkeypatch.setattr(pr_merge_update, "_backfill_cluster_cache", recorder.skip_backfill)
    return recorder


async def _merge_into_main(
    client: AsyncClient, factory: Factory, gh: FakeGitHub, repo: LocalGitRepo
) -> tuple[uuid.UUID, str, str]:
    full_name = f"acme/{unique_name('shop')}"
    gh.add_repo(full_name, "main", "develop")
    gh.pr_files[(full_name, 21)] = ["shop/orders/service.py", "shop/billing/api.py"]
    org = await seed_org(factory, github=gh)
    await seed_repo(factory, org.org_id, repo, full_name=full_name)
    delivery = f"merge-{uuid.uuid4()}"
    payload = pull_request_event(full_name, 21, merge_commit_sha="e" * 40, base_sha="f" * 40)
    assert (
        await deliver(client, "pull_request", payload, delivery_id=delivery)
    ).status_code == 200
    return org.org_id, full_name, delivery


async def test_the_worker_reads_the_merged_prs_files_from_github_for_the_cluster_diff(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    git_repo: LocalGitRepo,
    dispatch: Dispatch,
) -> None:
    org_id, full_name, delivery = await _merge_into_main(client, app_sessions, gh, git_repo)

    row = await webhook_log(app_sessions, delivery)
    assert row is not None and row.payload == {
        "action": "closed",
        "merged": True,
        "pr_number": 21,
        "full_name": full_name,
        "base_sha": "f" * 40,
        "head_sha": "e" * 40,
    }
    await pr_merge_update.handle_pr_merge_delivery(delivery)

    assert dispatch.changed_paths == [{"shop/orders/service.py", "shop/billing/api.py"}]
    assert bearer_tokens(gh, "/pulls/21/files") == [gh.issued_tokens[0]]
    (scan,) = dispatch.scans
    assert (scan["org_id"], scan["reason"], scan["delivery_id"]) == (
        org_id,
        "cache_miss",
        delivery,
    )


async def test_without_an_installation_the_worker_diffs_no_files_and_falls_back_to_a_scan(
    client: AsyncClient,
    app_sessions: Factory,
    gh: FakeGitHub,
    git_repo: LocalGitRepo,
    dispatch: Dispatch,
) -> None:
    org_id, _, delivery = await _merge_into_main(client, app_sessions, gh, git_repo)
    await set_installation(app_sessions, org_id, None)

    await pr_merge_update.handle_pr_merge_delivery(delivery)

    assert dispatch.changed_paths == [set()]
    assert bearer_tokens(gh, "/files") == []
    assert [s["reason"] for s in dispatch.scans] == ["cache_miss"]


async def test_a_merge_into_develop_leaves_only_an_audit_row(
    client: AsyncClient, app_sessions: Factory, gh: FakeGitHub, git_repo: LocalGitRepo
) -> None:
    full_name = f"acme/{unique_name('shop')}"
    org = await seed_org(app_sessions, github=gh)
    await seed_repo(app_sessions, org.org_id, git_repo, full_name=full_name)
    delivery = f"develop-{uuid.uuid4()}"

    payload = pull_request_event(full_name, 22, base="develop")
    assert (
        await deliver(client, "pull_request", payload, delivery_id=delivery)
    ).status_code == 200

    row = await webhook_log(app_sessions, delivery)
    assert row is not None
    assert (row.payload, row.status.value) == (None, "skipped")
