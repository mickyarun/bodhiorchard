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

"""Designer and tech-lead close-time Skill Points: complexity tiers, timing, wrong role."""

from __future__ import annotations

import pytest

from app.services.sp_designer import award_designer_sp_on_close
from app.services.sp_tech_arch import award_tech_arch_sp_on_close
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.integration.gamification_fakes.ledger_support import sp_ledger
from tests.integration.gamification_fakes.sp_support import (
    add_event,
    add_learning,
    new_bud,
    run_close_step,
)

pytestmark = pytest.mark.integration

FIGMA = {"source": "figma_url"}


@pytest.mark.parametrize(
    ("complexity", "drift", "on_time_amount"),
    [(3, 0.0, 0.25), (None, -2.0, 0.25), (4, -2.0, 0.5), (5, 0.1, None)],
    ids=["low-exactly-on-time", "unestimated-is-low", "high-tier", "late"],
)
async def test_designer_pay_follows_the_complexity_tier_and_the_design_drift(
    app_sessions: Factory, complexity: int | None, drift: float, on_time_amount: float | None
) -> None:
    org = await seed_org(app_sessions)
    des = await seed_member(app_sessions, org.org_id, "des", role="designer")
    bud_id = await new_bud(app_sessions, org.org_id, number=21, complexity=complexity)
    await add_event(app_sessions, org.org_id, bud_id, "design_updated", des, FIGMA)
    await add_learning(app_sessions, org.org_id, bud_id, drift={"design": drift})

    await run_close_step(app_sessions, org.org_id, bud_id, award_designer_sp_on_close)

    expected = {f"sp_designer:21:{des}": 0.25}
    if on_time_amount is not None:
        expected[f"sp_designer_ontime:21:{des}"] = on_time_amount
    assert await sp_ledger(app_sessions, org.org_id) == expected


async def test_only_designers_are_paid_and_repeated_edits_pay_once(
    app_sessions: Factory,
) -> None:
    org = await seed_org(app_sessions)
    des = await seed_member(app_sessions, org.org_id, "des", role="designer")
    dev = await seed_member(app_sessions, org.org_id, "dev", role="developer")
    bud_id = await new_bud(app_sessions, org.org_id, number=22)
    for actor in (des, des, dev):
        await add_event(app_sessions, org.org_id, bud_id, "design_updated", actor, FIGMA)

    await run_close_step(app_sessions, org.org_id, bud_id, award_designer_sp_on_close)
    await run_close_step(app_sessions, org.org_id, bud_id, award_designer_sp_on_close)

    assert await sp_ledger(app_sessions, org.org_id) == {f"sp_designer:22:{des}": 0.25}


@pytest.mark.parametrize(
    ("drift", "paid"),
    [(0.0, True), (0.1, False), (None, False)],
    ids=["exactly-on-estimate", "just-late", "no-metrics"],
)
async def test_tech_lead_is_paid_only_for_landing_tech_arch_within_estimate(
    app_sessions: Factory, drift: float | None, paid: bool
) -> None:
    org = await seed_org(app_sessions)
    lead = await seed_member(app_sessions, org.org_id, "lead", role="tech_lead")
    bud_id = await new_bud(app_sessions, org.org_id, number=23)
    move = {"from": "tech_arch", "to": "development"}
    await add_event(app_sessions, org.org_id, bud_id, "status_change", lead, move)
    if drift is not None:
        await add_learning(app_sessions, org.org_id, bud_id, drift={"tech_arch": drift})

    await run_close_step(app_sessions, org.org_id, bud_id, award_tech_arch_sp_on_close)

    expected = {f"sp_tl_techarch:23:{lead}": 0.25} if paid else {}
    assert await sp_ledger(app_sessions, org.org_id) == expected


async def test_a_pm_moving_the_bud_to_development_earns_no_tech_lead_credit(
    app_sessions: Factory,
) -> None:
    org = await seed_org(app_sessions)
    pm = await seed_member(app_sessions, org.org_id, "pm", role="pm")
    lead = await seed_member(app_sessions, org.org_id, "lead", role="tech_lead")
    bud_id = await new_bud(app_sessions, org.org_id, number=24)
    move = {"from": "tech_arch", "to": "development"}
    await add_event(app_sessions, org.org_id, bud_id, "status_change", pm, move)
    await add_event(app_sessions, org.org_id, bud_id, "status_change", lead, move)
    await add_learning(app_sessions, org.org_id, bud_id, drift={"tech_arch": -10.0})

    await run_close_step(app_sessions, org.org_id, bud_id, award_tech_arch_sp_on_close)

    assert await sp_ledger(app_sessions, org.org_id) == {}
