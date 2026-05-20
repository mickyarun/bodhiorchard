# Copyright 2025-2026 Arun Rajkumar
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
"""``sync_review_comments_to_github`` must post on every re-run.

Production bug: a code-review re-run stored its comments locally (the
BUD-tab badge count kept growing) but the GitHub PR never received a
second review. Cause was a sticky ``pr.metadata_["review_synced"]``
flag set by the first successful post and never cleared — every later
call short-circuited at the gate.

The fix removed the flag check entirely; per-comment dedup against
GitHub's echo runs via the ``review_id`` tag already covered by
``test_github_pr_sync_dedup``. These tests pin that the gate is gone:
two consecutive sync calls on the same PR both reach the
``create_pr_review`` step.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.pull_request import PRState
from app.services import github_pr_sync


def _make_pr(metadata: dict[str, Any] | None = None) -> MagicMock:
    pr = MagicMock()
    pr.id = uuid.uuid4()
    pr.state = PRState.OPEN
    pr.github_repo_full_name = "owner/api"
    pr.github_pr_number = 42
    pr.metadata_ = metadata or {}
    return pr


@pytest.fixture
def fake_db() -> AsyncMock:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.get = AsyncMock(return_value=MagicMock())  # org row
    return db


def _patch_sync_deps(create_pr_review_results: list[dict[str, Any] | None]):  # type: ignore[no-untyped-def]
    """Stub the heavy collaborators so the test focuses on the gate.

    ``create_pr_review_results`` queues per-call results so consecutive
    sync invocations can be exercised against the same stubs.
    """
    pr = _make_pr()
    pr_repo = MagicMock()
    pr_repo.list_for_bud = AsyncMock(return_value=[pr])

    client = MagicMock()
    client.create_pr_review = AsyncMock(side_effect=create_pr_review_results)
    tag = AsyncMock()

    return (
        patch.multiple(
            github_pr_sync,
            get_installation_token=AsyncMock(return_value="ghs_x"),
            GitHubClient=MagicMock(return_value=client),
            PullRequestRepository=MagicMock(return_value=pr_repo),
            _store_agent_comments_in_bud=AsyncMock(),
            _tag_agent_review_id=tag,
        ),
        client,
        pr,
        tag,
    )


@pytest.mark.asyncio
async def test_second_sync_call_still_posts_to_github(fake_db: AsyncMock) -> None:
    # Two consecutive calls with the same PR. Before the fix, the first
    # post set ``pr.metadata_["review_synced"]=True`` and the second was
    # silently skipped. Now both must reach ``create_pr_review``.
    comments = [{"repo": "api", "file": "a.py", "line": 1, "comment": "first"}]
    org_id, bud_id = uuid.uuid4(), uuid.uuid4()

    patches, client, _pr, tag = _patch_sync_deps([{"id": 100}, {"id": 200}])
    with patches:
        await github_pr_sync.sync_review_comments_to_github(bud_id, org_id, comments, fake_db)
        await github_pr_sync.sync_review_comments_to_github(bud_id, org_id, comments, fake_db)

    assert client.create_pr_review.await_count == 2, (
        "second sync was silently skipped — the review_synced gate is back"
    )
    # Tag step must run after EACH post with the corresponding fresh
    # review_id — otherwise the webhook handler can't dedupe the second
    # GitHub echo and ``code_review_comments`` inflates with duplicates.
    assert tag.await_count == 2, "tag step skipped on second post — echo dedup will fail"
    tagged_ids = sorted(
        call.kwargs.get("review_id", call.args[-1]) for call in tag.await_args_list
    )
    assert tagged_ids == [100, 200]


@pytest.mark.asyncio
async def test_sync_does_not_set_legacy_review_synced_flag(fake_db: AsyncMock) -> None:
    # Defensive guard: a refactor that re-introduces the flag will be
    # caught here before it ships. The PR's metadata must remain free of
    # ``review_synced`` after a successful post.
    comments = [{"repo": "api", "file": "a.py", "line": 1, "comment": "x"}]
    org_id, bud_id = uuid.uuid4(), uuid.uuid4()

    patches, _client, pr, _tag = _patch_sync_deps([{"id": 100}])
    with patches:
        await github_pr_sync.sync_review_comments_to_github(bud_id, org_id, comments, fake_db)

    assert "review_synced" not in (pr.metadata_ or {})


@pytest.mark.asyncio
async def test_legacy_review_synced_metadata_is_ignored(fake_db: AsyncMock) -> None:
    # Existing deploys may have PR rows with ``review_synced=True`` left
    # over from before this fix. Those PRs must still post on the next
    # run — otherwise the bug persists indefinitely for early customers.
    comments = [{"repo": "api", "file": "a.py", "line": 1, "comment": "x"}]
    org_id, bud_id = uuid.uuid4(), uuid.uuid4()

    pr = _make_pr(metadata={"review_synced": True, "other": "keep"})
    pr_repo = MagicMock()
    pr_repo.list_for_bud = AsyncMock(return_value=[pr])
    client = MagicMock()
    client.create_pr_review = AsyncMock(return_value={"id": 100})

    with patch.multiple(
        github_pr_sync,
        get_installation_token=AsyncMock(return_value="ghs_x"),
        GitHubClient=MagicMock(return_value=client),
        PullRequestRepository=MagicMock(return_value=pr_repo),
        _store_agent_comments_in_bud=AsyncMock(),
        _tag_agent_review_id=AsyncMock(),
    ):
        await github_pr_sync.sync_review_comments_to_github(bud_id, org_id, comments, fake_db)

    client.create_pr_review.assert_awaited_once()
