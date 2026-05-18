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

"""Unit tests for ``_build_pr_merge_replay_payload``.

The payload builder is the single gate that decides whether a webhook
delivery enters the per-(org, repo) Redis stream for feature
synthesis. The Phase-5 design intentionally restricts this to merges
into the tracked repo's ``main_branch`` — develop, uat, release, and
feature branches are recorded as ``status='skipped'`` audit rows but
never trigger a synth pass.

These tests pin every branch of that decision so a refactor can't
silently widen (or break) the filter.
"""

from __future__ import annotations

from typing import Any

import pytest

from app.api.v1.github_webhook import _build_pr_merge_replay_payload


def _payload(
    *,
    action: str = "closed",
    merged: bool = True,
    base_ref: str = "main",
    base_sha: str = "base-sha",
    head_sha: str = "head-sha",
    merge_commit_sha: str | None = "merge-commit-sha",
    pr_number: int = 42,
    full_name: str = "owner/repo",
) -> dict[str, Any]:
    """Construct a minimal pull_request webhook body for the builder."""
    return {
        "action": action,
        "pull_request": {
            "number": pr_number,
            "merged": merged,
            "merge_commit_sha": merge_commit_sha,
            "base": {"ref": base_ref, "sha": base_sha},
            "head": {"sha": head_sha},
        },
        "repository": {"full_name": full_name},
    }


def test_merge_into_main_branch_produces_replay_payload() -> None:
    """Happy path — merge into ``main`` (matches main_branch) → replay."""
    result = _build_pr_merge_replay_payload(_payload(base_ref="main"), main_branch="main")
    assert result is not None
    assert result["merged"] is True
    assert result["base_sha"] == "base-sha"
    assert result["head_sha"] == "merge-commit-sha"
    assert result["pr_number"] == 42
    assert result["full_name"] == "owner/repo"


def test_merge_into_master_when_main_branch_is_master() -> None:
    """A repo whose ``main_branch`` is configured as ``master`` should
    still match — the column name is generic, not hardcoded to ``main``.
    """
    result = _build_pr_merge_replay_payload(_payload(base_ref="master"), main_branch="master")
    assert result is not None


def test_merge_into_develop_is_skipped() -> None:
    """Non-main merges (develop, uat, release, feature/*) must not
    produce a replay payload — they're recorded as audit-only rows
    upstream and the consumer never sees them.
    """
    result = _build_pr_merge_replay_payload(_payload(base_ref="develop"), main_branch="main")
    assert result is None


def test_merge_into_uat_branch_is_skipped() -> None:
    """uat branch is in the BUD-lifecycle path, not the feature-synth
    path. Phase 5 deliberately doesn't drive ``feature_status`` from
    uat merges to avoid revert-tracking complexity.
    """
    result = _build_pr_merge_replay_payload(_payload(base_ref="release/uat"), main_branch="main")
    assert result is None


def test_merge_into_feature_branch_is_skipped() -> None:
    """Cross-branch merges (feature/foo → feature/bar, for instance)
    target neither main nor a release branch — definitely skipped.
    """
    result = _build_pr_merge_replay_payload(
        _payload(base_ref="feature/some-work"), main_branch="main"
    )
    assert result is None


def test_unconfigured_main_branch_skips_everything() -> None:
    """Repo with ``main_branch=None`` (never configured) → safe default
    of "don't synth" rather than "synth on every PR". Operator must
    set the branch before the page populates.
    """
    result = _build_pr_merge_replay_payload(_payload(base_ref="main"), main_branch=None)
    assert result is None


def test_non_closed_action_skipped() -> None:
    """``opened`` / ``synchronize`` etc. never trigger feature synth."""
    result = _build_pr_merge_replay_payload(_payload(action="opened"), main_branch="main")
    assert result is None


def test_closed_without_merge_skipped() -> None:
    """A PR closed without merging is not a synthesis event."""
    result = _build_pr_merge_replay_payload(_payload(merged=False), main_branch="main")
    assert result is None


def test_missing_head_sha_skipped() -> None:
    """Defensive: if neither ``merge_commit_sha`` nor ``head.sha`` is
    present the builder can't construct a valid replay payload.
    """
    payload = _payload(merge_commit_sha=None)
    payload["pull_request"]["head"]["sha"] = None
    result = _build_pr_merge_replay_payload(payload, main_branch="main")
    assert result is None


def test_falls_back_to_head_sha_when_merge_commit_sha_missing() -> None:
    """GitHub sends ``merge_commit_sha=None`` momentarily during
    rebase-merges; the builder should fall back to ``head.sha`` and
    still produce a valid payload when the base.ref matches.
    """
    result = _build_pr_merge_replay_payload(_payload(merge_commit_sha=None), main_branch="main")
    assert result is not None
    assert result["head_sha"] == "head-sha"


@pytest.mark.parametrize(
    "base_ref",
    ["main", "master", "production", "trunk"],
)
def test_arbitrary_main_branch_name_matches(base_ref: str) -> None:
    """The filter is exact string equality — any branch name configured
    as ``main_branch`` works (covers monorepo / legacy / org-specific
    naming).
    """
    result = _build_pr_merge_replay_payload(_payload(base_ref=base_ref), main_branch=base_ref)
    assert result is not None
