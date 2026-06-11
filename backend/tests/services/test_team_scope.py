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

"""Unit tests for ``team_scope.filter_candidates_by_team_ownership``.

The filter has three documented outcomes plus a JSONB-parser helper.
Each branch + parser path gets its own test so regressions show up
with a precise failure message rather than a vague assignment bug.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services import team_scope


def _user(uid: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=uid or uuid.uuid4())


def _impacted(*repo_ids: uuid.UUID) -> list[dict[str, str]]:
    return [{"repo_id": str(r), "repo_name": "x"} for r in repo_ids]


# ---------------------------------------------------------------------
# _extract_repo_ids — parser quirks
# ---------------------------------------------------------------------


def test_extract_empty_and_none() -> None:
    assert team_scope._extract_repo_ids(None) == ([], 0)
    assert team_scope._extract_repo_ids([]) == ([], 0)


def test_extract_skips_non_dict_entries() -> None:
    ids, discarded = team_scope._extract_repo_ids(["str-not-dict", 42, None])
    assert ids == []
    assert discarded == 3


def test_extract_skips_missing_or_non_string_repo_id() -> None:
    ids, discarded = team_scope._extract_repo_ids(
        [{"foo": "bar"}, {"repo_id": 123}, {"repo_id": None}]
    )
    assert ids == []
    assert discarded == 3


def test_extract_skips_bad_uuid_strings() -> None:
    ids, discarded = team_scope._extract_repo_ids(
        [{"repo_id": "not-a-uuid"}, {"repo_id": "also-bad"}]
    )
    assert ids == []
    assert discarded == 2


def test_extract_dedupes() -> None:
    u = uuid.uuid4()
    ids, discarded = team_scope._extract_repo_ids(
        [{"repo_id": str(u)}, {"repo_id": str(u)}, {"repo_id": str(u)}]
    )
    assert ids == [u]
    assert discarded == 0  # duplicates are not corruption, just noise


def test_extract_mixed_good_and_bad() -> None:
    good = uuid.uuid4()
    ids, discarded = team_scope._extract_repo_ids(
        [{"repo_id": str(good)}, "garbage", {"repo_id": "bad-uuid"}]
    )
    assert ids == [good]
    assert discarded == 2


# ---------------------------------------------------------------------
# filter_candidates_by_team_ownership — three outcomes
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_no_impacted_repos_returns_input_unchanged() -> None:
    candidates = [_user(), _user()]
    result = await team_scope.filter_candidates_by_team_ownership(
        db=AsyncMock(), org_id=uuid.uuid4(), candidates=candidates, impacted_repos=None
    )
    assert result.candidates is candidates
    assert result.applied is False
    assert result.fell_back is False
    assert result.input_malformed is False


@pytest.mark.asyncio
async def test_filter_all_malformed_input_flags_input_malformed() -> None:
    candidates = [_user()]
    result = await team_scope.filter_candidates_by_team_ownership(
        db=AsyncMock(),
        org_id=uuid.uuid4(),
        candidates=candidates,
        impacted_repos=[{"repo_id": "bad-uuid"}],
    )
    # Treated as "no impacted repos" for routing (applied=False) but the
    # malformed flag tells observers the difference between "BUD never
    # had impacted_repos" and "the JSONB is broken".
    assert result.candidates is candidates
    assert result.applied is False
    assert result.input_malformed is True
    assert result.discarded_count == 1


@pytest.mark.asyncio
async def test_filter_narrows_pool_when_team_member_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    u_in = _user()
    u_out = _user()
    repo = uuid.uuid4()

    async def fake_member_ids(self: object, repo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return {u_in.id}

    monkeypatch.setattr(team_scope.TeamRepository, "list_member_ids_for_repos", fake_member_ids)

    result = await team_scope.filter_candidates_by_team_ownership(
        db=AsyncMock(),
        org_id=uuid.uuid4(),
        candidates=[u_in, u_out],
        impacted_repos=_impacted(repo),
    )
    assert result.candidates == [u_in]
    assert result.applied is True
    assert result.fell_back is False
    assert result.team_pool_size == 1


@pytest.mark.asyncio
async def test_filter_falls_back_when_no_team_owns_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    u = _user()

    async def fake_member_ids(self: object, repo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return set()  # no team owns the repo

    monkeypatch.setattr(team_scope.TeamRepository, "list_member_ids_for_repos", fake_member_ids)

    result = await team_scope.filter_candidates_by_team_ownership(
        db=AsyncMock(),
        org_id=uuid.uuid4(),
        candidates=[u],
        impacted_repos=_impacted(uuid.uuid4()),
    )
    # Wider pool returned + fell_back flag set so the banner can warn.
    assert result.candidates == [u]
    assert result.applied is True
    assert result.fell_back is True
    assert result.team_pool_size == 0


@pytest.mark.asyncio
async def test_filter_falls_back_when_no_role_match_in_owning_team(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    u = _user()
    other = uuid.uuid4()  # team has a member but it's not in the role pool

    async def fake_member_ids(self: object, repo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return {other}

    monkeypatch.setattr(team_scope.TeamRepository, "list_member_ids_for_repos", fake_member_ids)

    result = await team_scope.filter_candidates_by_team_ownership(
        db=AsyncMock(),
        org_id=uuid.uuid4(),
        candidates=[u],
        impacted_repos=_impacted(uuid.uuid4()),
    )
    assert result.candidates == [u]
    assert result.applied is True
    assert result.fell_back is True
    assert result.team_pool_size == 1  # team had members, just not the right role


# ---------------------------------------------------------------------
# user_is_in_owning_team — continuity helper
# ---------------------------------------------------------------------


@pytest.mark.asyncio
async def test_user_is_in_owning_team_true_when_membership_present(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid = uuid.uuid4()

    async def fake_member_ids(self: object, repo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return {uid}

    monkeypatch.setattr(team_scope.TeamRepository, "list_member_ids_for_repos", fake_member_ids)

    assert await team_scope.user_is_in_owning_team(
        db=AsyncMock(),
        org_id=uuid.uuid4(),
        user_id=uid,
        impacted_repos=_impacted(uuid.uuid4()),
    )


@pytest.mark.asyncio
async def test_user_is_in_owning_team_false_when_not_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_member_ids(self: object, repo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return {uuid.uuid4()}  # some other user is in the team

    monkeypatch.setattr(team_scope.TeamRepository, "list_member_ids_for_repos", fake_member_ids)

    assert not await team_scope.user_is_in_owning_team(
        db=AsyncMock(),
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        impacted_repos=_impacted(uuid.uuid4()),
    )


@pytest.mark.asyncio
async def test_user_is_in_owning_team_true_when_no_impacted_repos() -> None:
    # No repos to validate against → user trivially eligible. Matches
    # the pre-team-scope behaviour for legacy BUDs.
    assert await team_scope.user_is_in_owning_team(
        db=AsyncMock(),
        org_id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        impacted_repos=None,
    )
