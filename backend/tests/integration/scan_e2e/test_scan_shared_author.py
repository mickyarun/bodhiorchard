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

"""Two orgs scanning code by the same git author.

Skill extraction turns each git author into a member of the scanning org,
and user emails are unique across orgs, so the second org's scan used to
fail outright on the author the first org already owns.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from pathlib import Path

import pytest
from httpx import AsyncClient

from app.models.scan_phase import ScanPhase
from app.models.scan_run_enums import RepoRunStatus, StepStatus
from app.repositories.user import UserRepository
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.git_repo import LocalGitRepo
from tests.fakes.seed import auth_headers, seed_org, seed_repo
from tests.integration.scan_e2e.scan_support import (
    SYNTHESIS_MARKER,
    Factory,
    load_outcome,
    require,
    start_scan_over_http,
    synthesis_writing,
)

pytestmark = [pytest.mark.integration, pytest.mark.slow]


async def _scan_in_new_org(
    client: AsyncClient, factory: Factory, repo: LocalGitRepo
) -> tuple[RepoRunStatus, StepStatus | None, str | None, uuid.UUID]:
    org = await seed_org(factory)
    repo_id = await seed_repo(factory, org.org_id, repo)
    scan_id = await start_scan_over_http(client, auth_headers(org.owner_id, org.org_id), repo_id)
    outcome = await load_outcome(factory, org.org_id, scan_id)
    steps = {step.phase: step.status for step in outcome.steps}
    return outcome.run.status, steps.get(ScanPhase.SKILL_EXTRACTION), outcome.run.error, org.org_id


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="author owned by another org fails skill extraction; "
    "fixed by branch fix/scan-author-in-another-org",
)
async def test_second_org_scanning_the_same_author_still_completes(
    client: AsyncClient,
    app_sessions: Factory,
    mcp_claude: FakeClaudeRunner,
    git_repo_factory: Callable[..., LocalGitRepo],
    data_dir: Path,
) -> None:
    author = f"shared-{uuid.uuid4().hex[:8]}@example.test"
    first = git_repo_factory("shop-api", author_email=author)
    second = git_repo_factory("shop-web", author_email=author)
    mcp_claude.when(SYNTHESIS_MARKER, synthesis_writing(1))

    first_status, _, _, first_org = await _scan_in_new_org(client, app_sessions, first)
    require(first_status is RepoRunStatus.DONE, "the first org's scan should complete")
    status, skills, error, second_org = await _scan_in_new_org(client, app_sessions, second)

    assert status is RepoRunStatus.DONE, error
    assert skills is StepStatus.DONE
    async with app_sessions() as db:
        users = UserRepository(db)
        owner = await users.get_by_email(author)
        assert owner is not None
        assert await users.get_membership(owner.id, first_org) is not None
        assert await users.get_membership(owner.id, second_org) is None
