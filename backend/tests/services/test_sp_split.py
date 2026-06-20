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

"""Tests for ``sp_split`` — the weighted fixed-pool SP divider.

Pins the largest-remainder maths (shares sum to the pool), the
zero-weight exclusion (trivial todos earn nothing), the per-recipient
dedup contract, and the swallow-on-error guarantee.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.sp_split import award_split_sp, compute_shares


def test_proportional_split_sums_to_pool() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    shares = compute_shares(1.0, {a: 3.0, b: 1.0})
    assert shares == {a: 0.75, b: 0.25}
    assert round(sum(shares.values()), 2) == 1.0


def test_even_three_way_split_sums_to_pool() -> None:
    users = [uuid.uuid4() for _ in range(3)]
    shares = compute_shares(1.0, {u: 1.0 for u in users})
    # 1.00 / 3 → two get 0.33, one gets 0.34 (largest-remainder), sum == 1.00
    assert sorted(shares.values()) == [0.33, 0.33, 0.34]
    assert round(sum(shares.values()), 2) == 1.0


def test_zero_weight_recipient_excluded() -> None:
    real, trivial = uuid.uuid4(), uuid.uuid4()
    shares = compute_shares(1.0, {real: 1.0, trivial: 0.0})
    assert shares == {real: 1.0}


def test_single_recipient_gets_full_pool() -> None:
    u = uuid.uuid4()
    assert compute_shares(1.0, {u: 5.0}) == {u: 1.0}


def test_empty_or_nonpositive_weights_yield_no_shares() -> None:
    assert compute_shares(1.0, {}) == {}
    assert compute_shares(1.0, {uuid.uuid4(): 0.0}) == {}
    assert compute_shares(0.0, {uuid.uuid4(): 1.0}) == {}


def test_more_recipients_than_cents_skips_the_remainder() -> None:
    # pool 0.01 (1 cent) across 3 people → only one cent to give.
    users = [uuid.uuid4() for _ in range(3)]
    shares = compute_shares(0.01, {u: 1.0 for u in users})
    assert len(shares) == 1
    assert sum(shares.values()) == 0.01


@pytest.mark.asyncio
async def test_award_split_sp_credits_each_recipient() -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    org_id = uuid.uuid4()

    with patch("app.services.sp_split.award_sp", new=AsyncMock(return_value=1.0)) as mock_award:
        awarded = await award_split_sp(
            MagicMock(),
            org_id,
            pool=1.0,
            weights={a: 1.0, b: 1.0},
            source="sp_bud_shipped",
            ref_prefix="sp_bud_shipped",
            bud_number=29,
        )

    assert awarded == 2
    refs = {c.kwargs["source_ref"] for c in mock_award.await_args_list}
    assert refs == {f"sp_bud_shipped:29:{a}", f"sp_bud_shipped:29:{b}"}


@pytest.mark.asyncio
async def test_award_split_sp_no_recipients_short_circuits() -> None:
    with patch("app.services.sp_split.award_sp") as mock_award:
        awarded = await award_split_sp(
            MagicMock(),
            uuid.uuid4(),
            pool=1.0,
            weights={uuid.uuid4(): 0.0},
            source="sp_bud_shipped",
            ref_prefix="sp_bud_shipped",
            bud_number=1,
        )

    assert awarded == 0
    mock_award.assert_not_awaited()


@pytest.mark.asyncio
async def test_award_split_sp_dedup_returns_zero() -> None:
    with patch("app.services.sp_split.award_sp", new=AsyncMock(return_value=None)):
        awarded = await award_split_sp(
            MagicMock(),
            uuid.uuid4(),
            pool=1.0,
            weights={uuid.uuid4(): 1.0, uuid.uuid4(): 1.0},
            source="sp_bud_shipped",
            ref_prefix="sp_bud_shipped",
            bud_number=1,
        )

    assert awarded == 0


@pytest.mark.asyncio
async def test_award_split_sp_swallows_per_recipient_error() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    async def _flaky(*args: object, **kwargs: object) -> float | None:
        if kwargs["user_id"] == b:
            raise RuntimeError("simulated hiccup")
        return 1.0

    with patch("app.services.sp_split.award_sp", new=AsyncMock(side_effect=_flaky)):
        awarded = await award_split_sp(
            MagicMock(),
            uuid.uuid4(),
            pool=3.0,
            weights={a: 1.0, b: 1.0, c: 1.0},
            source="sp_bud_shipped",
            ref_prefix="sp_bud_shipped",
            bud_number=1,
        )

    assert awarded == 2
