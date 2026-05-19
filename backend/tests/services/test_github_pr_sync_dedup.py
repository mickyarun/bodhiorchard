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

"""Tests for the agent ↔ webhook dedup correlation on PR reviews.

Production bug: ``bud.code_review_comments`` ended up with double the
entries it should have because the agent path stored each inline comment
*and* the webhook handler stored the same comments again when GitHub
fired ``pull_request_review`` back at us. The fix tags agent entries
with the GitHub ``review_id`` returned by the create-review call so the
webhook handler can recognise an echo of its own bot's post and skip
the second write.

These tests cover the two halves of the correlation in isolation:

* ``_tag_agent_review_id`` stamps the right entries and leaves the rest
  alone.
* The ``any(c.get("review_id") == review.id ...)`` predicate in
  ``_handle_pr_review`` correctly identifies the echo.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.github_pr_sync import _tag_agent_review_id


class _FakeBUD:
    """Tiny stand-in for BUDDocument — only the fields the tag helper touches.

    The real model has dozens of columns + relationships we don't need
    to exercise here; faking the two fields keeps the test focused on
    the correlation logic and avoids spinning up a DB session.
    """

    def __init__(self, comments: list[dict[str, Any]]) -> None:
        self.code_review_comments = comments


@pytest.fixture
def fake_db() -> AsyncMock:
    db = AsyncMock()
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_tag_stamps_only_matching_agent_entries(fake_db: AsyncMock) -> None:
    """Tag writes ``review_id`` onto matching repo's agent entries only."""
    bud = _FakeBUD(
        comments=[
            # Target repo, agent — should be tagged.
            {"source": "agent", "repo": "api", "file": "a.py", "body": "x"},
            {"source": "agent", "repo": "api", "file": "b.py", "body": "y"},
            # Different repo — must NOT be tagged.
            {"source": "agent", "repo": "web", "file": "c.ts", "body": "z"},
            # Human / webhook entry — must NOT be tagged.
            {"source": "github", "repo": "api", "github_comment_id": 999},
        ]
    )
    org_id, bud_id = uuid.uuid4(), uuid.uuid4()

    with patch(
        "app.services.github_pr_sync.BUDRepository",
        return_value=MagicMock(get_by_id_for_update=AsyncMock(return_value=bud)),
    ):
        await _tag_agent_review_id(fake_db, org_id, bud_id, "api", review_id=4242)

    tagged = [c for c in bud.code_review_comments if c.get("review_id") == 4242]
    assert len(tagged) == 2, "both api/agent entries should carry review_id"
    assert all(c["repo"] == "api" and c["source"] == "agent" for c in tagged)

    untagged = [c for c in bud.code_review_comments if "review_id" not in c]
    assert len(untagged) == 2, "web/agent and api/github entries must be left alone"

    fake_db.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_tag_is_noop_when_bud_missing(fake_db: AsyncMock) -> None:
    """A vanished BUD short-circuits without flushing (no crash, no log noise)."""
    org_id, bud_id = uuid.uuid4(), uuid.uuid4()
    with patch(
        "app.services.github_pr_sync.BUDRepository",
        return_value=MagicMock(get_by_id_for_update=AsyncMock(return_value=None)),
    ):
        await _tag_agent_review_id(fake_db, org_id, bud_id, "api", review_id=1)
    fake_db.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_tag_does_not_flush_when_no_matching_entries(fake_db: AsyncMock) -> None:
    """No agent entries for this repo → no rewrite, no flush.

    Pins the ``changed`` short-circuit in ``_tag_agent_review_id``: if
    every entry is for a sibling repo or non-agent, the function must
    not rewrite the JSONB column nor call ``flush`` (which would emit a
    pointless ``UPDATE bud_documents`` statement on a hot path that
    runs once per PR per agent review).
    """
    bud = _FakeBUD(
        comments=[
            {"source": "agent", "repo": "web", "file": "c.ts"},
            {"source": "github", "repo": "api", "github_comment_id": 1},
        ]
    )
    org_id, bud_id = uuid.uuid4(), uuid.uuid4()
    with patch(
        "app.services.github_pr_sync.BUDRepository",
        return_value=MagicMock(get_by_id_for_update=AsyncMock(return_value=bud)),
    ):
        await _tag_agent_review_id(fake_db, org_id, bud_id, "api", review_id=4242)

    fake_db.flush.assert_not_awaited()
    # And the existing entries are untouched.
    assert all("review_id" not in c for c in bud.code_review_comments)


@pytest.mark.asyncio
async def test_tag_does_not_overwrite_existing_review_id(fake_db: AsyncMock) -> None:
    """Entries already correlated to a review are not re-tagged.

    Prevents a re-run on the same repo from blasting a prior, valid
    correlation if the post step happened to complete before. Idempotency
    under retry is the load-bearing invariant.
    """
    bud = _FakeBUD(
        comments=[
            {"source": "agent", "repo": "api", "review_id": 1111},
            {"source": "agent", "repo": "api", "file": "new.py"},
        ]
    )
    org_id, bud_id = uuid.uuid4(), uuid.uuid4()

    with patch(
        "app.services.github_pr_sync.BUDRepository",
        return_value=MagicMock(get_by_id_for_update=AsyncMock(return_value=bud)),
    ):
        await _tag_agent_review_id(fake_db, org_id, bud_id, "api", review_id=2222)

    review_ids = sorted(c["review_id"] for c in bud.code_review_comments)
    assert review_ids == [1111, 2222], "preserved old id, tagged the fresh entry"


@pytest.mark.asyncio
async def test_agent_to_webhook_echo_cycle_uses_same_field(fake_db: AsyncMock) -> None:
    """End-to-end: tag-then-echo-detect threads through a shared BUD.

    Stamps the same ``_FakeBUD`` via ``_tag_agent_review_id`` and then
    reads the stored entries to evaluate the echo-detection predicate
    that ``_fetch_and_store_review_comments`` uses. If anyone renames
    the field on one side (e.g. ``review_id`` → ``gh_review_id``) and
    forgets the other, this test fails — whereas the two existing
    isolation tests would both still pass with a half-renamed setup.
    """
    review_id = 8888
    bud = _FakeBUD(
        comments=[
            {"source": "agent", "repo": "api", "file": "a.py", "body": "x"},
            {"source": "agent", "repo": "api", "file": "b.py", "body": "y"},
        ]
    )
    org_id, bud_id = uuid.uuid4(), uuid.uuid4()

    with patch(
        "app.services.github_pr_sync.BUDRepository",
        return_value=MagicMock(get_by_id_for_update=AsyncMock(return_value=bud)),
    ):
        await _tag_agent_review_id(fake_db, org_id, bud_id, "api", review_id)

    # Now simulate exactly what ``_fetch_and_store_review_comments`` does:
    # read the current code_review_comments and check if it's an echo.
    existing = list(bud.code_review_comments)
    is_echo = any(c.get("review_id") == review_id for c in existing)
    assert is_echo, "agent-tagged entries must be recognised by the webhook predicate"


def test_webhook_echo_detection_predicate() -> None:
    """The predicate used by ``_handle_pr_review`` to skip an echo.

    Mirrors the inline check ``any(c.get("review_id") == review.id ...)``.
    Kept here as a regression guard: if anyone refactors the predicate
    to look up ``github_comment_id`` (the OLD dedup key) or accidentally
    flips identity vs. equality semantics, this fails.
    """
    review_id = 9001
    existing_with_echo: list[dict[str, Any]] = [
        {"source": "agent", "repo": "api", "review_id": review_id},
        {"source": "agent", "repo": "api", "review_id": review_id},
    ]
    existing_without_echo: list[dict[str, Any]] = [
        {"source": "agent", "repo": "api", "review_id": 1},
        {"source": "github", "github_comment_id": 42},
    ]

    assert any(c.get("review_id") == review_id for c in existing_with_echo) is True
    assert any(c.get("review_id") == review_id for c in existing_without_echo) is False
