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

"""Setup for the PR-merge rescan tests: a GitHub-App org scanned once.

The bare repository plays GitHub. Before an agent run the app points a
GitHub-App org's clone at ``https://github.com/...`` (with a fresh App
token), which the guard keeps git from reaching, so after the first scan the
helper points ``origin`` back at the bare repository, as GitHub would answer.
Each test tracks its own GitHub name: the webhook finds the repo by name
alone, so two orgs tracking one name would see each other's deliveries.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from httpx import AsyncClient

from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript, ToolCall
from tests.fakes.git_repo import LocalGitRepo, git
from tests.fakes.github import FakeGitHub
from tests.fakes.seed import WEBHOOK_SECRET, auth_headers, seed_org, seed_repo
from tests.fakes.signing import signed_github_webhook
from tests.integration.scan_e2e.scan_support import (
    NARROW_MARKER,
    SYNTHESIS_MARKER,
    Factory,
    feature_params,
    require,
    start_scan_over_http,
    synthesis_writing,
)

WEBHOOK_URL = "/api/v1/webhooks/github"
TAX = "shop/billing/tax.py"


@dataclass(frozen=True)
class Merged:
    """A GitHub-App org whose repo has had one full scan."""

    org_id: uuid.UUID
    repo_id: uuid.UUID
    scan_id: uuid.UUID
    base_sha: str
    full_name: str


async def scanned_on_github(
    client: AsyncClient,
    factory: Factory,
    claude: FakeClaudeRunner,
    github: FakeGitHub,
    repo: LocalGitRepo,
) -> Merged:
    """Scan ``repo`` for a new GitHub-App org; narrow runs write one feature."""
    full_name = f"acme/shop-{uuid.uuid4().hex[:8]}"
    github.add_repo(full_name)
    org = await seed_org(factory, github=github)
    repo_id = await seed_repo(factory, org.org_id, repo, full_name=full_name)
    narrow = ToolCall(SYNTHESIS_MARKER, lambda run: feature_params(run, 0, "Taxed"))
    claude.when(NARROW_MARKER, AgentScript.ok("Reconciled.", narrow))
    claude.when(SYNTHESIS_MARKER, synthesis_writing(2))
    headers = auth_headers(org.owner_id, org.org_id)
    scan_id = await start_scan_over_http(client, headers, repo_id)
    origin_url = git(repo.work, "remote", "get-url", "origin")
    require(origin_url.endswith(f"github.com/{full_name}.git"), origin_url)
    git(repo.work, "remote", "set-url", "origin", str(repo.origin))
    return Merged(org.org_id, repo_id, scan_id, repo.head("main"), full_name)


async def deliver(
    client: AsyncClient, payload: dict[str, Any], delivery: str, secret: str = WEBHOOK_SECRET
) -> int:
    """POST one signed ``pull_request`` delivery; return the status code."""
    body, headers = signed_github_webhook(secret, "pull_request", payload, delivery)
    return (await client.post(WEBHOOK_URL, content=body, headers=headers)).status_code


def narrow_prompts(claude: FakeClaudeRunner) -> list[str]:
    """Prompts of the narrow (PR-merge) synthesis runs so far."""
    return [run.prompt for run in claude.runs if NARROW_MARKER in run.prompt]
