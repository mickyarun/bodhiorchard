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

"""The monthly quiz champion payout: SP only, ties split, safe to run every day."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.repositories.organization import OrganizationRepository
from app.services import quiz_monthly_rollup
from app.services.quiz_monthly_rollup import finalize_org_month, sweep_once
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.integration.gamification_fakes.ledger_support import sp_ledger, xp_event_count
from tests.integration.gamification_fakes.quiz_fake_support import (
    deactivate,
    enable_quiz,
    seed_score,
)
from tests.integration.gamification_fakes.streak_support import install_clock

pytestmark = pytest.mark.integration

FEB = "2026-02"


async def _players(factory: Factory, *names: str) -> tuple[uuid.UUID, list[uuid.UUID]]:
    org = await seed_org(factory)
    return org.org_id, [await seed_member(factory, org.org_id, n) for n in names]


def _paid(ledger: dict[str, float], org_id: uuid.UUID, month: str) -> dict[str, float]:
    prefix = f"sp_quiz_monthly:{org_id}:{month}:"
    return {ref.removeprefix(prefix): amt for ref, amt in ledger.items() if ref.startswith(prefix)}


async def test_the_top_scorer_wins_the_whole_prize_once_and_no_xp_moves(
    app_sessions: Factory,
) -> None:
    org_id, (ana, ben) = await _players(app_sessions, "ana", "ben")
    await seed_score(app_sessions, org_id, ana, FEB, points=300, correct=2)
    await seed_score(app_sessions, org_id, ben, FEB, points=290, correct=3)

    first = await finalize_org_month(org_id, period_month=FEB, amount=1.5)
    again = await finalize_org_month(org_id, period_month=FEB, amount=1.5)

    assert (first, again) == (1, 0)
    assert _paid(await sp_ledger(app_sessions, org_id), org_id, FEB) == {str(ana): 1.5}
    assert await xp_event_count(app_sessions, org_id) == 0


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ([(250, 2, 900), (250, 2, 900)], [0.5, 0.5]),
        ([(250, 2, 901), (250, 2, 900)], [None, 1.0]),
        ([(250, 2, 900), (250, 3, 9000)], [None, 1.0]),
        ([(100, 1, 50), (100, 1, 50), (100, 1, 50)], [0.33, 0.33, 0.33]),
    ],
    ids=["exact-tie-splits", "faster-wins", "more-correct-wins", "three-way-tie-rounds-down"],
)
async def test_ties_split_only_when_points_correct_and_time_all_match(
    app_sessions: Factory, scores: list[tuple[int, int, int]], expected: list[float | None]
) -> None:
    org_id, players = await _players(app_sessions, *[f"p{i}" for i in range(len(scores))])
    for user, (points, correct, time_ms) in zip(players, scores, strict=True):
        await seed_score(
            app_sessions, org_id, user, FEB, points=points, correct=correct, time_ms=time_ms
        )

    await finalize_org_month(org_id, period_month=FEB, amount=1.0)

    paid = _paid(await sp_ledger(app_sessions, org_id), org_id, FEB)
    assert [paid.get(str(u)) for u in players] == expected


async def test_a_champion_who_left_hands_the_prize_to_the_next_active_player(
    app_sessions: Factory,
) -> None:
    org_id, (gone, stays) = await _players(app_sessions, "gone", "stays")
    await seed_score(app_sessions, org_id, gone, FEB, points=500, correct=4)
    await seed_score(app_sessions, org_id, stays, FEB, points=100, correct=1)
    await deactivate(app_sessions, gone)

    await finalize_org_month(org_id, period_month=FEB, amount=1.0)

    assert _paid(await sp_ledger(app_sessions, org_id), org_id, FEB) == {str(stays): 1.0}


@pytest.mark.parametrize(
    ("points", "amount"),
    [(None, 1.0), (0, 1.0), (300, 0.0)],
    ids=["nobody", "all-wrong", "no-prize"],
)
async def test_no_payout_without_a_positive_score_or_a_prize(
    app_sessions: Factory, points: int | None, amount: float
) -> None:
    org_id, (ana,) = await _players(app_sessions, "ana")
    if points is not None:
        await seed_score(app_sessions, org_id, ana, FEB, points=points, correct=0)

    assert await finalize_org_month(org_id, period_month=FEB, amount=amount) == 0
    assert await sp_ledger(app_sessions, org_id) == {}


@pytest.mark.parametrize(
    ("now", "paid_month"),
    [
        (datetime(2026, 3, 1, 0, 0, 30, tzinfo=UTC), "2026-02"),
        (datetime(2026, 3, 31, 23, 59, tzinfo=UTC), "2026-02"),
        (datetime(2026, 1, 1, 0, 1, tzinfo=UTC), "2025-12"),
    ],
    ids=["first-minute-of-march", "last-minute-of-march", "new-year"],
)
async def test_the_daily_sweep_pays_the_month_that_just_ended(
    app_sessions: Factory, monkeypatch: pytest.MonkeyPatch, now: datetime, paid_month: str
) -> None:
    org_id, (ana, ben) = await _players(app_sessions, "ana", "ben")
    disabled_id, (cy,) = await _players(app_sessions, "cy")
    await enable_quiz(app_sessions, disabled_id, enabled=False)
    for month in ("2025-12", "2026-01", "2026-02", "2026-03"):
        winner = ana if month == paid_month else ben
        await seed_score(app_sessions, org_id, winner, month, points=200, correct=2)
        await seed_score(app_sessions, disabled_id, cy, month, points=200, correct=2)

    async def only_these(_: OrganizationRepository) -> list[uuid.UUID]:
        return [org_id, disabled_id]

    monkeypatch.setattr(OrganizationRepository, "list_all_ids", only_these)
    install_clock(monkeypatch, quiz_monthly_rollup, now)

    assert await sweep_once() == 1
    assert await sweep_once() == 0

    ledger = await sp_ledger(app_sessions, org_id)
    assert ledger == {f"sp_quiz_monthly:{org_id}:{paid_month}:{ana}": 1.0}
    assert await sp_ledger(app_sessions, disabled_id) == {}
