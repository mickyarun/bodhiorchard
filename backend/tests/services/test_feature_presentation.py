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

"""Unit tests for ``app.services.feature_presentation``.

The resolver pulls SHAs from THREE columns — ``created_at_sha``,
``last_seen_sha``, ``deactivated_at_sha`` — into one bulk PR lookup.
These tests pin (a) which columns contribute, (b) dedup across
columns and across features, (c) the short-circuit on empty input,
(d) that ``is_active`` does NOT gate any column (active features
contribute their creation/last-seen SHAs too).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any
from unittest.mock import MagicMock

import pytest

from app.services import feature_presentation as mod


@dataclass
class _StubFeature:
    """Just the fields :func:`resolve_pr_meta_for_features` reads."""

    is_active: bool = True
    created_at_sha: str | None = None
    last_seen_sha: str | None = None
    deactivated_at_sha: str | None = None


@pytest.fixture
def captured_shas() -> list[list[str]]:
    """Records every SHA list the helper passes into the repo method."""
    return []


@pytest.fixture
def _patched_repo(monkeypatch: pytest.MonkeyPatch, captured_shas: list[list[str]]) -> None:
    """Stand-in ``PullRequestRepository`` whose ``map_shas_to_pr_meta``
    appends each invocation's SHA list and returns a deterministic
    mapping. Avoids hitting Postgres for what is pure routing logic.
    """

    class _FakeRepo:
        def __init__(self, db: Any, *, org_id: uuid.UUID) -> None:
            del db, org_id

        async def map_shas_to_pr_meta(self, shas: list[str]) -> dict[str, tuple[int, str | None]]:
            captured_shas.append(list(shas))
            return {sha: (i, f"https://x/{sha}") for i, sha in enumerate(shas, start=100)}

    monkeypatch.setattr(mod, "PullRequestRepository", _FakeRepo)


async def test_resolve_pr_meta_collects_from_all_three_sha_columns(
    _patched_repo: None, captured_shas: list[list[str]]
) -> None:
    """Active row's created_at_sha + last_seen_sha + an inactive row's
    deactivated_at_sha all land in one batched lookup, deduped + sorted.
    """
    features = [
        _StubFeature(
            is_active=True,
            created_at_sha="sha-created",
            last_seen_sha="sha-last-seen",
        ),
        _StubFeature(
            is_active=False,
            created_at_sha="sha-created",  # same as row 1 — must dedup
            last_seen_sha="sha-dead-last",
            deactivated_at_sha="sha-deactivated",
        ),
    ]
    db = MagicMock()
    result = await mod.resolve_pr_meta_for_features(
        db,
        org_id=uuid.uuid4(),
        features=features,  # type: ignore[arg-type]
    )

    # All four distinct SHAs, sorted, single call.
    assert captured_shas == [["sha-created", "sha-deactivated", "sha-dead-last", "sha-last-seen"]]
    # Result dict round-trips every SHA the fake echoed.
    assert "sha-created" in result
    assert "sha-deactivated" in result


async def test_resolve_pr_meta_active_row_contributes_its_shas(
    _patched_repo: None, captured_shas: list[list[str]]
) -> None:
    """An active row with no deactivation SHA still contributes
    creation + last-seen SHAs — those drive the "Created by PR / Last
    touched by PR" lineage row.
    """
    features = [
        _StubFeature(
            is_active=True,
            created_at_sha="sha-c",
            last_seen_sha="sha-l",
            deactivated_at_sha=None,
        ),
    ]
    await mod.resolve_pr_meta_for_features(
        MagicMock(),
        org_id=uuid.uuid4(),
        features=features,  # type: ignore[arg-type]
    )
    assert captured_shas == [["sha-c", "sha-l"]]


async def test_resolve_pr_meta_short_circuits_when_no_sha_anywhere(
    _patched_repo: None, captured_shas: list[list[str]]
) -> None:
    """No SHA on any column → no DB hit, empty dict.

    Important so the per-page hot path doesn't pay a Postgres round
    trip when the page is entirely legacy rows (pre-this-column).
    """
    features = [
        _StubFeature(is_active=True),  # all three SHA fields None
        _StubFeature(is_active=False),  # also all None — operator soft-delete with no SHA
    ]
    db = MagicMock()
    result = await mod.resolve_pr_meta_for_features(
        db,
        org_id=uuid.uuid4(),
        features=features,  # type: ignore[arg-type]
    )

    assert captured_shas == []  # repo never touched
    assert result == {}


async def test_resolve_pr_meta_empty_features_list_is_a_noop(
    _patched_repo: None, captured_shas: list[list[str]]
) -> None:
    """Empty features list short-circuits the same way."""
    result = await mod.resolve_pr_meta_for_features(MagicMock(), org_id=uuid.uuid4(), features=[])
    assert result == {}
    assert captured_shas == []


async def test_resolve_pr_meta_deduplicates_when_three_columns_share_sha(
    _patched_repo: None, captured_shas: list[list[str]]
) -> None:
    """A feature created + last-touched + soft-deleted in one merge SHA
    (e.g. a synthesised cluster that turned out to be a duplicate, all
    in one PR) hits the repo with exactly ONE entry.
    """
    sha = "single-sha"
    features = [
        _StubFeature(
            is_active=False,
            created_at_sha=sha,
            last_seen_sha=sha,
            deactivated_at_sha=sha,
        ),
    ]
    await mod.resolve_pr_meta_for_features(
        MagicMock(),
        org_id=uuid.uuid4(),
        features=features,  # type: ignore[arg-type]
    )
    assert captured_shas == [[sha]]
