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

"""Tests for ``stage_award.award_stage_xp_to_contributors``.

The stage-promotion XP loop is the only XP event with non-trivial maths
(splitting a fixed pool across N contributors) and the only path that
populates the new ``reward_events.bud_id`` column. These tests pin down
the per-user amount calculation, the per-(user, bud, stage) dedup
contract, and the no-contributors short-circuit so a regression can't
silently mis-credit a release event.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.stage_award import award_stage_xp_to_contributors


def _award_xp_mock_returning(result: object = object()) -> AsyncMock:
    """An ``award_xp`` mock that returns a truthy XPAwardResult each call."""
    return AsyncMock(return_value=result)


@pytest.mark.asyncio
async def test_single_contributor_gets_full_pool_for_develop() -> None:
    """One contributor on develop merge → +5 XP."""
    bud_id = uuid.uuid4()
    user_id = uuid.uuid4()

    with (
        patch(
            "app.services.stage_award.get_bud_contributors",
            new=AsyncMock(return_value={user_id}),
        ),
        patch("app.services.stage_award.award_xp") as mock_award,
    ):
        mock_award.side_effect = _award_xp_mock_returning().side_effect
        mock_award.return_value = object()

        awarded = await award_stage_xp_to_contributors(
            MagicMock(), uuid.uuid4(), bud_id, "develop"
        )

    assert awarded == 1
    call = mock_award.await_args
    assert call.kwargs["amount"] == 5
    assert call.kwargs["source"] == "xp_stage_develop"
    assert call.kwargs["source_ref"] == f"xp_stage:develop:{bud_id}:{user_id}"
    assert call.kwargs["bud_id"] == bud_id


@pytest.mark.asyncio
async def test_two_contributors_split_uat_pool_evenly() -> None:
    """Two contributors on uat merge → +7.5 each."""
    bud_id = uuid.uuid4()
    contributors = {uuid.uuid4(), uuid.uuid4()}

    with (
        patch(
            "app.services.stage_award.get_bud_contributors",
            new=AsyncMock(return_value=contributors),
        ),
        patch("app.services.stage_award.award_xp") as mock_award,
    ):
        mock_award.return_value = object()

        awarded = await award_stage_xp_to_contributors(MagicMock(), uuid.uuid4(), bud_id, "uat")

    assert awarded == 2
    for call in mock_award.await_args_list:
        assert call.kwargs["amount"] == 7.5
        assert call.kwargs["source"] == "xp_stage_uat"


@pytest.mark.asyncio
async def test_three_contributors_prod_pool_rounded_to_two_decimal() -> None:
    """Three on prod merge → +8.33 each (25 / 3 = 8.333…, rounded)."""
    contributors = {uuid.uuid4() for _ in range(3)}

    with (
        patch(
            "app.services.stage_award.get_bud_contributors",
            new=AsyncMock(return_value=contributors),
        ),
        patch("app.services.stage_award.award_xp") as mock_award,
    ):
        mock_award.return_value = object()

        await award_stage_xp_to_contributors(MagicMock(), uuid.uuid4(), uuid.uuid4(), "prod")

    for call in mock_award.await_args_list:
        assert call.kwargs["amount"] == 8.33


@pytest.mark.asyncio
async def test_no_contributors_short_circuits_without_calling_award_xp() -> None:
    """Empty contributor set → 0 awards, no ``award_xp`` calls."""
    with (
        patch(
            "app.services.stage_award.get_bud_contributors",
            new=AsyncMock(return_value=set()),
        ),
        patch("app.services.stage_award.award_xp") as mock_award,
    ):
        awarded = await award_stage_xp_to_contributors(
            MagicMock(), uuid.uuid4(), uuid.uuid4(), "develop"
        )

    assert awarded == 0
    mock_award.assert_not_awaited()


@pytest.mark.asyncio
async def test_dedup_returns_zero_awards_when_xp_already_credited() -> None:
    """If ``award_xp`` returns None (deduped) for all contributors, awarded=0."""
    contributors = {uuid.uuid4(), uuid.uuid4()}

    with (
        patch(
            "app.services.stage_award.get_bud_contributors",
            new=AsyncMock(return_value=contributors),
        ),
        patch("app.services.stage_award.award_xp", new=AsyncMock(return_value=None)),
    ):
        awarded = await award_stage_xp_to_contributors(
            MagicMock(), uuid.uuid4(), uuid.uuid4(), "uat"
        )

    assert awarded == 0


@pytest.mark.asyncio
async def test_partial_dedup_counts_only_new_awards() -> None:
    """When ``award_xp`` returns None for one and a result for the other → awarded=1."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()

    async def _side_effect(*args: object, **kwargs: object) -> object | None:
        # First contributor: already credited (dedup); second: fresh award.
        if kwargs["user_id"] == user_a:
            return None
        return object()

    with (
        patch(
            "app.services.stage_award.get_bud_contributors",
            new=AsyncMock(return_value={user_a, user_b}),
        ),
        patch("app.services.stage_award.award_xp", new=AsyncMock(side_effect=_side_effect)),
    ):
        awarded = await award_stage_xp_to_contributors(
            MagicMock(), uuid.uuid4(), uuid.uuid4(), "prod"
        )

    assert awarded == 1


@pytest.mark.asyncio
async def test_award_xp_exception_does_not_abort_remaining_contributors() -> None:
    """One contributor's failure must not block the rest of the loop."""
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    user_c = uuid.uuid4()

    async def _flaky(*args: object, **kwargs: object) -> object:
        if kwargs["user_id"] == user_b:
            raise RuntimeError("simulated DB hiccup")
        return object()

    with (
        patch(
            "app.services.stage_award.get_bud_contributors",
            new=AsyncMock(return_value={user_a, user_b, user_c}),
        ),
        patch("app.services.stage_award.award_xp", new=AsyncMock(side_effect=_flaky)),
    ):
        awarded = await award_stage_xp_to_contributors(
            MagicMock(), uuid.uuid4(), uuid.uuid4(), "develop"
        )

    # Two awards land (user_a + user_c), user_b's RuntimeError is swallowed.
    assert awarded == 2


@pytest.mark.asyncio
async def test_extreme_contributor_count_rounds_per_user_to_zero_and_short_circuits() -> None:
    """When ``pool / N`` rounds to 0.0 (huge contributor count vs tiny pool),
    the loop short-circuits without making zero-amount awards.

    Develop pool is 5 XP. With 1001 contributors, 5/1001 = 0.005, rounded to
    0.0. The helper must NOT call ``award_xp(amount=0.0)`` for each — that's
    wasted work and pollutes the audit trail with zero-value rows.
    """
    contributors = {uuid.uuid4() for _ in range(1001)}

    with (
        patch(
            "app.services.stage_award.get_bud_contributors",
            new=AsyncMock(return_value=contributors),
        ),
        patch("app.services.stage_award.award_xp") as mock_award,
    ):
        awarded = await award_stage_xp_to_contributors(
            MagicMock(), uuid.uuid4(), uuid.uuid4(), "develop"
        )

    assert awarded == 0
    mock_award.assert_not_awaited()
