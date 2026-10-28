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

"""The developer quality bonus and over-budget penalty, settled once per BUD.

Complexity 3 has a budget of four valid testing bugs. Production and
rejected bugs never count; "on time" is a development drift of at most zero.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bug import BugStatus, BugType
from app.models.dev_activity import DevActivityLog
from app.services.dev_quality_sp import award_quality_and_threshold_sp
from app.services.xp_service import award_quality_bonus
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.integration.gamification_fakes.ledger_support import sp_balance, sp_ledger
from tests.integration.gamification_fakes.sp_support import (
    CloseStep,
    add_bugs,
    add_learning,
    new_bud,
    run_close_step,
)

pytestmark = pytest.mark.integration

BUD_NUMBER = 31


def _for(*devs: uuid.UUID) -> CloseStep:
    async def step(db: AsyncSession, org_id: uuid.UUID, bud: BUDDocument) -> None:
        await award_quality_and_threshold_sp(db, org_id, bud, set(devs), org_config=None)

    return step


async def _bud_with_bugs(
    factory: Factory, testing_bugs: int, drift: float | None
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    org = await seed_org(factory)
    dev = await seed_member(factory, org.org_id, "dev")
    bud_id = await new_bud(factory, org.org_id, number=BUD_NUMBER, complexity=3)
    await add_bugs(factory, org.org_id, bud_id, org.owner_id, testing_bugs)
    if drift is not None:
        await add_learning(factory, org.org_id, bud_id, drift={"development": drift})
    return org.org_id, bud_id, dev


@pytest.mark.parametrize(
    ("bugs", "drift", "expected"),
    [
        (4, 0.0, {"sp_quality": 0.5}),
        (0, -30.0, {"sp_quality": 0.5}),
        (5, -30.0, {"sp_bug_threshold": -0.25}),
        (4, 0.01, {}),
        (4, None, {}),
    ],
    ids=["at-budget-on-time", "clean-early", "one-over-budget", "late", "no-metrics"],
)
async def test_bonus_needs_bugs_within_budget_and_an_on_time_finish(
    app_sessions: Factory, bugs: int, drift: float | None, expected: dict[str, float]
) -> None:
    org_id, bud_id, dev = await _bud_with_bugs(app_sessions, bugs, drift)

    await run_close_step(app_sessions, org_id, bud_id, _for(dev))

    ledger = await sp_ledger(app_sessions, org_id)
    assert {ref.split(":")[0]: amount for ref, amount in ledger.items()} == expected


async def test_production_and_rejected_bugs_do_not_eat_the_budget(app_sessions: Factory) -> None:
    org_id, bud_id, dev = await _bud_with_bugs(app_sessions, 4, -1.0)
    reporter = await seed_member(app_sessions, org_id, "qa", role="qa")
    await add_bugs(
        app_sessions, org_id, bud_id, reporter, 2, bug_type=BugType.PRODUCTION, first_number=10
    )
    await add_bugs(
        app_sessions, org_id, bud_id, reporter, 3, status=BugStatus.REJECTED, first_number=20
    )

    await run_close_step(app_sessions, org_id, bud_id, _for(dev))

    assert await sp_ledger(app_sessions, org_id) == {f"sp_quality:{BUD_NUMBER}:{dev}": 0.5}


async def test_the_bonus_is_paid_once_per_bud_and_the_penalty_floors_at_zero(
    app_sessions: Factory,
) -> None:
    org_id, bud_id, dev = await _bud_with_bugs(app_sessions, 0, 0.0)
    over_id, over_bud, over_dev = await _bud_with_bugs(app_sessions, 9, 0.0)

    for _ in range(3):
        await run_close_step(app_sessions, org_id, bud_id, _for(dev))
        await run_close_step(app_sessions, over_id, over_bud, _for(over_dev))

    assert await sp_balance(app_sessions, org_id, dev) == 0.5
    assert await sp_ledger(app_sessions, over_id) == {f"sp_bug_threshold:31:{over_dev}": -0.25}
    assert await sp_balance(app_sessions, over_id, over_dev) == 0.0


async def test_no_developers_means_no_bonus_and_no_penalty(app_sessions: Factory) -> None:
    org_id, bud_id, _ = await _bud_with_bugs(app_sessions, 9, 0.0)

    await run_close_step(app_sessions, org_id, bud_id, _for())

    assert await sp_ledger(app_sessions, org_id) == {}


async def _activity(
    factory: Factory,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    user: uuid.UUID,
    commits: int,
    errors: int,
) -> None:
    async with factory() as db:
        kinds = ["commit"] * commits + ["tool_error"] * errors
        db.add_all(
            DevActivityLog(
                org_id=org_id, bud_id=bud_id, user_id=user, event_type=kind, source="hook"
            )
            for kind in kinds
        )
        await db.commit()


async def _legacy_bonus(
    factory: Factory, org_id: uuid.UUID, bud_id: uuid.UUID, dev: uuid.UUID
) -> int:
    async with factory() as db:
        xp = await award_quality_bonus(db, user_id=dev, org_id=org_id, bud_id=bud_id)
        await db.commit()
        return xp


@pytest.mark.parametrize(
    ("commits", "errors", "xp", "sp"),
    [(4, 1, 24, 0.0), (9, 1, 27, 0.5)],
    ids=["score-80-no-sp", "score-90-sp"],
)
async def test_the_completion_bonus_pays_sp_only_above_an_80_score(
    app_sessions: Factory, commits: int, errors: int, xp: int, sp: float
) -> None:
    org_id, bud_id, dev = await _bud_with_bugs(app_sessions, 0, None)
    await _activity(app_sessions, org_id, bud_id, dev, commits, errors)

    assert await _legacy_bonus(app_sessions, org_id, bud_id, dev) == xp
    assert await sp_balance(app_sessions, org_id, dev) == sp


@pytest.mark.xfail(
    strict=True,
    raises=AssertionError,
    reason="quality SP is paid twice per BUD: award_quality_bonus still pays sp_quality under "
    "its own source_ref next to the close-time bonus; reported, no fix branch yet",
)
async def test_a_developer_gets_one_quality_bonus_per_bud_across_both_award_paths(
    app_sessions: Factory,
) -> None:
    org_id, bud_id, dev = await _bud_with_bugs(app_sessions, 0, -5.0)
    await _activity(app_sessions, org_id, bud_id, dev, 5, 0)

    await _legacy_bonus(app_sessions, org_id, bud_id, dev)
    await run_close_step(app_sessions, org_id, bud_id, _for(dev))

    assert await sp_balance(app_sessions, org_id, dev) == 0.5
