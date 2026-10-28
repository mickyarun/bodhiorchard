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

"""Manual code_review -> testing through PATCH.

When every impacted repo has a merged PR the move is the same as the
webhook's auto-advance and needs nothing. Otherwise the caller is
bypassing the PR-merge gate and must give a reason, which is recorded.
"""

from __future__ import annotations

import uuid

import pytest
from httpx import AsyncClient

from app.models.bud import BUDStatus
from app.models.pull_request import PRState, PullRequest
from app.models.tracked_repository import TrackedRepository
from tests.integration.bud_lifecycle_reads import (
    load_bud,
    timeline,
)
from tests.integration.bud_lifecycle_support import (
    Factory,
    add_bud,
    add_member,
    as_user,
    new_org,
    stub_externals,
)

pytestmark = pytest.mark.integration


async def _bud_with_pr(factory: Factory, pr_state: PRState | None) -> tuple[uuid.UUID, uuid.UUID]:
    """Org + a code_review BUD on one impacted repo with a PR in ``pr_state``."""
    org = await new_org(factory)
    async with factory() as db:
        repo = TrackedRepository(org_id=org, path=f"/repos/{uuid.uuid4().hex}", name="api")
        db.add(repo)
        await db.commit()
        repo_id = repo.id
    bud_id = await add_bud(
        factory,
        org,
        status=BUDStatus.CODE_REVIEW,
        impacted_repos=[{"repo_id": str(repo_id), "repo_name": "api"}],
    )
    if pr_state is not None:
        async with factory() as db:
            db.add(
                PullRequest(
                    org_id=org,
                    bud_id=bud_id,
                    repo_id=repo_id,
                    github_pr_number=7,
                    github_pr_id=int(uuid.uuid4().int % 10**12),
                    github_repo_full_name="acme/api",
                    title="BUD-001 change",
                    html_url="https://example.invalid/pr/7",
                    head_branch="bud-001/change",
                    base_branch="main",
                    author_github_login="dev",
                    state=pr_state,
                )
            )
            await db.commit()
    return org, bud_id


async def _advance(
    client: AsyncClient, factory: Factory, org: uuid.UUID, bud_id: uuid.UUID, **extra: str
) -> int:
    """PATCH the BUD to testing as a PM; return the status code."""
    pm = await add_member(factory, org, "pm")
    with stub_externals():
        res = await client.patch(
            f"/api/v1/buds/{bud_id}",
            json={"status": "testing", **extra},
            headers=as_user(pm, org),
        )
    return res.status_code


async def test_all_prs_merged_needs_no_reason(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """Merged everywhere: advance freely, no override recorded."""
    org, bud_id = await _bud_with_pr(pg_session_factory, PRState.MERGED)

    assert await _advance(client, pg_session_factory, org, bud_id) == 200
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.TESTING
    assert await timeline(pg_session_factory, bud_id, "status_override") == []


@pytest.mark.parametrize("pr_state", [PRState.OPEN, PRState.CLOSED, None])
@pytest.mark.parametrize("reason", [None, "", "   "])
async def test_bypassing_the_merge_gate_needs_a_reason(
    client: AsyncClient,
    pg_session_factory: Factory,
    pr_state: PRState | None,
    reason: str | None,
) -> None:
    """Open, closed-unmerged or missing PR: no (or blank) reason is a 400."""
    org, bud_id = await _bud_with_pr(pg_session_factory, pr_state)
    extra = {} if reason is None else {"status_override_reason": reason}

    assert await _advance(client, pg_session_factory, org, bud_id, **extra) == 400
    assert (await load_bud(pg_session_factory, bud_id)).status is BUDStatus.CODE_REVIEW
    assert await timeline(pg_session_factory, bud_id, "status_change") == []


async def test_bypass_reason_is_trimmed_and_recorded(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """The override lands in the timeline next to the status change."""
    org, bud_id = await _bud_with_pr(pg_session_factory, PRState.OPEN)

    code = await _advance(
        client, pg_session_factory, org, bud_id, status_override_reason="  docs only  "
    )

    assert code == 200
    assert await timeline(pg_session_factory, bud_id, "status_override") == [
        {"from": "code_review", "to": "testing", "reason": "docs only"}
    ]


async def test_bud_without_impacted_repos_also_needs_a_reason(
    client: AsyncClient, pg_session_factory: Factory
) -> None:
    """No impacted repos means nothing merged: the bypass rule applies."""
    org = await new_org(pg_session_factory)
    bud_id = await add_bud(pg_session_factory, org, status=BUDStatus.CODE_REVIEW)

    assert await _advance(client, pg_session_factory, org, bud_id) == 400
    assert (
        await _advance(
            client, pg_session_factory, org, bud_id, status_override_reason="manual merge"
        )
        == 200
    )
