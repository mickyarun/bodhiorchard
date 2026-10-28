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

"""QA and PM close-time Skill Points: reduced credit, taper, budget edges, wrong role."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bug import BugStatus
from app.services.sp_pm import award_pm_sp_on_close
from app.services.sp_qa import award_qa_sp_on_close
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.integration.gamification_fakes.ledger_support import sp_ledger
from tests.integration.gamification_fakes.sp_support import (
    add_bugs,
    add_event,
    add_learning,
    new_bud,
    run_close_step,
)

pytestmark = pytest.mark.integration


async def _qa_close(db: AsyncSession, org_id: uuid.UUID, bud: BUDDocument) -> None:
    await award_qa_sp_on_close(db, org_id, bud, org_config=None)


def _assigned(user_id: uuid.UUID) -> dict[str, Any]:
    return {"phase": "testing", "assignee_id": str(user_id), "role": "qa"}


async def test_qa_who_skipped_test_cases_gets_the_reduced_credit(app_sessions: Factory) -> None:
    org = await seed_org(app_sessions)
    qa = await seed_member(app_sessions, org.org_id, "qa", role="qa")
    bud_id = await new_bud(app_sessions, org.org_id, number=11)
    await add_event(app_sessions, org.org_id, bud_id, "assigned", qa, _assigned(qa))
    skip = {"kind": "qa_skip", "phase": "testing", "skipped_case_ids": ["tc-3"]}
    await add_event(app_sessions, org.org_id, bud_id, "status_override", qa, skip)

    await run_close_step(app_sessions, org.org_id, bud_id, _qa_close)
    await run_close_step(app_sessions, org.org_id, bud_id, _qa_close)

    assert await sp_ledger(app_sessions, org.org_id) == {f"sp_qa_tests:11:{qa}": 0.25}


async def test_bugs_at_the_budget_or_padded_with_rejects_earn_no_over_budget_credit(
    app_sessions: Factory,
) -> None:
    org = await seed_org(app_sessions)
    qa = await seed_member(app_sessions, org.org_id, "qa", role="qa")
    bud_id = await new_bud(app_sessions, org.org_id, number=12, complexity=2)
    await add_bugs(app_sessions, org.org_id, bud_id, qa, 2)
    await add_bugs(
        app_sessions, org.org_id, bud_id, qa, 3, status=BugStatus.REJECTED, first_number=3
    )

    await run_close_step(app_sessions, org.org_id, bud_id, _qa_close)

    assert await sp_ledger(app_sessions, org.org_id) == {}


async def test_qa_rules_skip_members_without_the_qa_role(app_sessions: Factory) -> None:
    org = await seed_org(app_sessions)
    dev = await seed_member(app_sessions, org.org_id, "dev", role="developer")
    bud_id = await new_bud(app_sessions, org.org_id, number=13, complexity=1)
    await add_event(app_sessions, org.org_id, bud_id, "assigned", dev, _assigned(dev))
    await add_bugs(app_sessions, org.org_id, bud_id, dev, 4)

    await run_close_step(app_sessions, org.org_id, bud_id, _qa_close)

    assert await sp_ledger(app_sessions, org.org_id) == {}


async def test_a_custom_org_budget_decides_the_over_budget_credit(app_sessions: Factory) -> None:
    org = await seed_org(app_sessions)
    qa = await seed_member(app_sessions, org.org_id, "qa", role="qa")
    bud_id = await new_bud(app_sessions, org.org_id, number=14, complexity=3)
    await add_bugs(app_sessions, org.org_id, bud_id, qa, 2)
    config = {"qa": {"bug_threshold_by_complexity": {"3": 1}}}

    async def close(db: AsyncSession, org_id: uuid.UUID, bud: BUDDocument) -> None:
        await award_qa_sp_on_close(db, org_id, bud, org_config=config)

    await run_close_step(app_sessions, org.org_id, bud_id, close)

    assert await sp_ledger(app_sessions, org.org_id) == {f"sp_qa_threshold:14:{qa}": 0.25}


@pytest.mark.parametrize(
    ("estimate", "cycle_days", "tech_arch_drift", "expected"),
    [
        (10.0, 13.0, 0.0, {"sp_pm_requirement": 1.0, "sp_pm_techspec": 0.25}),
        (4.0, 5.2, 3.0, {"sp_pm_requirement": 1.0}),
        (10.0, 14.0, 4.0, {"sp_pm_requirement": 0.5}),
        (10.0, 15.0, -1.0, {"sp_pm_requirement": 0.5, "sp_pm_techspec": 0.25}),
        (10.0, 16.0, 0.5, {}),
    ],
    ids=["30pct-full", "30pct-odd-estimate-full", "40pct-half", "50pct-half", "60pct-none"],
)
async def test_the_pm_credit_tapers_with_the_overrun_and_techspec_needs_drift_at_most_zero(
    app_sessions: Factory,
    estimate: float,
    cycle_days: float,
    tech_arch_drift: float,
    expected: dict[str, float],
) -> None:
    org = await seed_org(app_sessions)
    pm = await seed_member(app_sessions, org.org_id, "pm", role="pm")
    bud_id = await new_bud(app_sessions, org.org_id, number=15)
    move = {"from": "bud", "to": "design"}
    await add_event(app_sessions, org.org_id, bud_id, "status_change", pm, move)
    await add_learning(
        app_sessions,
        org.org_id,
        bud_id,
        drift={"tech_arch": tech_arch_drift},
        estimated_days=estimate,
        cycle_time_days=cycle_days,
    )

    await run_close_step(app_sessions, org.org_id, bud_id, award_pm_sp_on_close)

    ledger = await sp_ledger(app_sessions, org.org_id)
    assert {ref.split(":")[0]: amount for ref, amount in ledger.items()} == expected


@pytest.mark.parametrize("mover_role", ["developer", None], ids=["developer", "system"])
async def test_no_pm_credit_when_a_non_pm_or_the_system_moved_it_to_design(
    app_sessions: Factory, mover_role: str | None
) -> None:
    org = await seed_org(app_sessions)
    pm = await seed_member(app_sessions, org.org_id, "pm", role="pm")
    mover = await seed_member(app_sessions, org.org_id, "dev") if mover_role else None
    bud_id = await new_bud(app_sessions, org.org_id, number=16)
    move = {"from": "bud", "to": "design"}
    await add_event(app_sessions, org.org_id, bud_id, "status_change", mover, move)
    await add_event(app_sessions, org.org_id, bud_id, "status_change", pm, move)
    await add_learning(app_sessions, org.org_id, bud_id, drift={"tech_arch": -5.0})

    await run_close_step(app_sessions, org.org_id, bud_id, award_pm_sp_on_close)

    assert await sp_ledger(app_sessions, org.org_id) == {}
