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

"""Tests for ``github_webhook_handler._resolve_release_stage``.

The "NULL stage-branch column = no XP credit" contract is the safety net
that prevents a stage merge from awarding XP on a repo that hasn't been
configured for that stage. These tests pin that contract per stage so a
future refactor can't accidentally fall through to a default-on path.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.github_webhook_handler import _resolve_release_stage


def _repo(
    *,
    develop_branch: str | None = None,
    uat_branch: str | None = None,
    main_branch: str | None = None,
) -> MagicMock:
    return MagicMock(
        develop_branch=develop_branch,
        uat_branch=uat_branch,
        main_branch=main_branch,
    )


def test_returns_develop_when_branch_matches() -> None:
    """Merge into the configured develop branch → 'develop'."""
    assert (
        _resolve_release_stage(_repo(develop_branch="develop"), "develop", uat_enabled=False)
        == "develop"
    )


def test_returns_uat_when_branch_matches_and_uat_enabled() -> None:
    """Merge into the configured uat branch + org has UAT on → 'uat'."""
    assert (
        _resolve_release_stage(_repo(uat_branch="release/uat"), "release/uat", uat_enabled=True)
        == "uat"
    )


def test_returns_prod_when_main_branch_matches() -> None:
    """Merge into the configured main branch → 'prod'."""
    assert _resolve_release_stage(_repo(main_branch="main"), "main", uat_enabled=False) == "prod"


@pytest.mark.parametrize("base_ref", ["develop", "develop/main", "feature/develop"])
def test_no_develop_branch_returns_none(base_ref: str) -> None:
    """NULL ``develop_branch`` → no credit, even when base_ref looks like 'develop'."""
    repo = _repo(develop_branch=None, uat_branch="release/uat", main_branch="main")
    assert _resolve_release_stage(repo, base_ref, uat_enabled=True) is None


def test_no_uat_branch_returns_none_for_uat_base() -> None:
    """NULL ``uat_branch`` → merge into ``release/uat`` does not credit."""
    repo = _repo(uat_branch=None, main_branch="main", develop_branch="develop")
    assert _resolve_release_stage(repo, "release/uat", uat_enabled=True) is None


def test_uat_branch_set_but_org_disabled_returns_none() -> None:
    """``uat_branch`` set but org flag off → no UAT credit; fall through to next stage."""
    repo = _repo(uat_branch="release/uat")
    assert _resolve_release_stage(repo, "release/uat", uat_enabled=False) is None


def test_no_main_branch_returns_none_for_main_base() -> None:
    """NULL ``main_branch`` → merge into ``main`` does not credit."""
    repo = _repo(main_branch=None, develop_branch="develop", uat_branch="release/uat")
    assert _resolve_release_stage(repo, "main", uat_enabled=True) is None


def test_all_branches_null_returns_none() -> None:
    """A tracked repo with no stage branches configured opts out entirely."""
    assert _resolve_release_stage(_repo(), "main", uat_enabled=True) is None
    assert _resolve_release_stage(_repo(), "develop", uat_enabled=True) is None
    assert _resolve_release_stage(_repo(), "release/uat", uat_enabled=True) is None


def test_unrelated_base_ref_returns_none() -> None:
    """Merge into a feature branch ignores stage detection."""
    repo = _repo(develop_branch="develop", uat_branch="release/uat", main_branch="main")
    assert _resolve_release_stage(repo, "feature/foo", uat_enabled=True) is None
