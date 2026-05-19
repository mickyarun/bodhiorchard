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

"""Tests for the dev → code_review TODO completion gate.

Before this gate, ``check_all_repos_have_prs`` would flip a BUD to
``code_review`` the moment every impacted repo had a PR open — even if
the developer hadn't ticked off any of the BUD's TODOs (including the
code-review TODO the tech-arch agent emits). The code-review agent then
ran against half-finished work and produced noise.

These tests pin down the gate semantics on the function in isolation,
faking the repository and DB layer so we exercise the control flow
without standing up a database session.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.bud import BUDStatus
from app.services.pr_auto_transition import check_all_repos_have_prs


class _FakeBUD:
    """Stand-in for BUDDocument carrying only the fields the gate reads."""

    def __init__(self, *, status: BUDStatus, impacted_repos: list[dict[str, Any]]) -> None:
        self.id = uuid.uuid4()
        self.status = status
        self.impacted_repos = impacted_repos
        self.metadata_: dict[str, Any] | None = None


@pytest.fixture
def fake_db() -> AsyncMock:
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


def _patch_repos(
    repo_ids_with_prs: set[str],
    remaining_todos: int,
):
    """Patch the three repos check_all_repos_have_prs touches.

    Keeps the test body focused on the gate semantics. PullRequest +
    Tracked repo fakes only need to return the inputs the function
    consumes; BUDTodoRepository is the one driving the gate.
    """
    pr_repo = MagicMock(
        get_repo_ids_with_prs=AsyncMock(return_value=repo_ids_with_prs),
    )
    tr_repo = MagicMock(
        get_active_id_path_name=AsyncMock(return_value=[]),
    )
    todo_repo = MagicMock(
        count_remaining_for_bud=AsyncMock(return_value=remaining_todos),
    )
    return (
        patch("app.services.pr_auto_transition.PullRequestRepository", return_value=pr_repo),
        patch("app.services.pr_auto_transition.BUDTodoRepository", return_value=todo_repo),
        patch(
            "app.repositories.tracked_repository.TrackedRepoRepository",
            return_value=tr_repo,
        ),
    )


@pytest.mark.asyncio
async def test_gate_blocks_when_todos_remain(fake_db: AsyncMock) -> None:
    """PR-on-every-repo but remaining TODOs > 0 → no transition.

    Also asserts the gate-blocked path has no side effects: a future
    regression that moved ``record_event`` or ``create_agent_task_for_stage``
    above the gate would silently mis-report a status change. Asserting
    both mocks were never called pins the "block means block" contract.
    """
    repo_id = str(uuid.uuid4())
    bud = _FakeBUD(
        status=BUDStatus.DEVELOPMENT,
        impacted_repos=[{"repo_id": repo_id, "repo_name": "api"}],
    )

    p1, p2, p3 = _patch_repos(repo_ids_with_prs={repo_id}, remaining_todos=2)
    record_event_mock = AsyncMock()
    create_agent_task_mock = AsyncMock()
    with (
        p1,
        p2,
        p3,
        patch("app.services.pr_auto_transition.record_event", record_event_mock),
        patch(
            "app.services.bud_agent_trigger.create_agent_task_for_stage",
            create_agent_task_mock,
        ),
    ):
        await check_all_repos_have_prs(fake_db, uuid.uuid4(), bud)

    assert bud.status is BUDStatus.DEVELOPMENT, "remaining TODOs must hold the BUD in development"
    record_event_mock.assert_not_awaited()
    create_agent_task_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate_passes_when_all_todos_completed(fake_db: AsyncMock) -> None:
    """PR-on-every-repo AND zero remaining TODOs → transition fires."""
    repo_id = str(uuid.uuid4())
    bud = _FakeBUD(
        status=BUDStatus.DEVELOPMENT,
        impacted_repos=[{"repo_id": repo_id, "repo_name": "api"}],
    )

    p1, p2, p3 = _patch_repos(repo_ids_with_prs={repo_id}, remaining_todos=0)
    # The transition path also fires record_event and create_agent_task_for_stage;
    # stub them so the test doesn't try to write to a real DB / job queue.
    with (
        p1,
        p2,
        p3,
        patch("app.services.pr_auto_transition.record_event", AsyncMock()),
        patch(
            "app.services.bud_agent_trigger.create_agent_task_for_stage",
            AsyncMock(),
        ),
    ):
        await check_all_repos_have_prs(fake_db, uuid.uuid4(), bud)

    assert bud.status is BUDStatus.CODE_REVIEW, "BUD must advance once the gate is clear"


@pytest.mark.asyncio
async def test_gate_not_evaluated_when_a_repo_lacks_pr(fake_db: AsyncMock) -> None:
    """If even one impacted repo has no PR, the PR check short-circuits.

    The TODO gate is downstream of the PR check, so this confirms we
    don't pay the extra DB roundtrip when the outer condition fails.
    Also catches regressions that move the gate above the PR check
    (which would block a transition the developer never requested).
    """
    repo_a, repo_b = str(uuid.uuid4()), str(uuid.uuid4())
    bud = _FakeBUD(
        status=BUDStatus.DEVELOPMENT,
        impacted_repos=[
            {"repo_id": repo_a, "repo_name": "api"},
            {"repo_id": repo_b, "repo_name": "web"},
        ],
    )

    todo_repo = MagicMock(
        count_remaining_for_bud=AsyncMock(return_value=0),
    )
    pr_repo = MagicMock(
        # Only repo_a has a PR — repo_b is still missing.
        get_repo_ids_with_prs=AsyncMock(return_value={repo_a}),
    )

    with (
        patch("app.services.pr_auto_transition.PullRequestRepository", return_value=pr_repo),
        patch("app.services.pr_auto_transition.BUDTodoRepository", return_value=todo_repo),
    ):
        await check_all_repos_have_prs(fake_db, uuid.uuid4(), bud)

    assert bud.status is BUDStatus.DEVELOPMENT
    todo_repo.count_remaining_for_bud.assert_not_awaited()


@pytest.mark.asyncio
async def test_gate_noop_when_bud_already_past_development(fake_db: AsyncMock) -> None:
    """A BUD that's already in code_review (or later) must not flip again."""
    bud = _FakeBUD(
        status=BUDStatus.CODE_REVIEW,
        impacted_repos=[{"repo_id": str(uuid.uuid4()), "repo_name": "api"}],
    )

    p1, p2, p3 = _patch_repos(repo_ids_with_prs=set(), remaining_todos=0)
    with p1, p2, p3:
        await check_all_repos_have_prs(fake_db, uuid.uuid4(), bud)

    assert bud.status is BUDStatus.CODE_REVIEW
