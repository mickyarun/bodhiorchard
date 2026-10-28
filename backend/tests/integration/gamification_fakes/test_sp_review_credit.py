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

"""Code-review Skill Points: valid, non-self reviews by developers and tech leads only."""

from __future__ import annotations

import json
import uuid

import pytest

from app.models.bud import BUDDocument
from app.services.code_review_sp import award_code_review_sp
from app.services.sp_developer import award_developer_sp_on_close
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.integration.gamification_fakes.ledger_support import sp_ledger
from tests.integration.gamification_fakes.sp_support import (
    add_todo,
    new_bud,
    run_close_step,
    set_github_login,
)

pytestmark = pytest.mark.integration


async def _reviewer(
    factory: Factory, org_id: uuid.UUID, login: str, role: str | None
) -> uuid.UUID:
    user_id = await seed_member(factory, org_id, login, role=role)
    await set_github_login(factory, user_id, f"{login}-{user_id.hex[:6]}")
    return user_id


def _login(name: str, user_id: uuid.UUID) -> str:
    return f"{name}-{user_id.hex[:6]}"


def _review(
    login: str, body: str = "Cap the retries; this loops forever on 5xx."
) -> dict[str, str]:
    return {"author": login, "body": body}


async def test_the_judge_strips_a_rubber_stamp_review_but_pays_the_real_one(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    org = await seed_org(app_sessions)
    dev = await seed_member(app_sessions, org.org_id, "dev")
    lead = await _reviewer(app_sessions, org.org_id, "lead", "tech_lead")
    peer = await _reviewer(app_sessions, org.org_id, "peer", "developer")
    lead_login, peer_login = _login("lead", lead), _login("peer", peer)
    reviews = [_review(lead_login), _review(peer_login, "LGTM")]
    bud_id = await new_bud(app_sessions, org.org_id, number=5, reviews=reviews)
    await add_todo(app_sessions, org.org_id, bud_id, dev, "Build export", sequence=1)
    verdict = {"review_validity": {lead_login: True, peer_login: False}}
    fake_claude.enqueue(AgentScript.ok(json.dumps(verdict)))

    await run_close_step(app_sessions, org.org_id, bud_id, award_developer_sp_on_close)

    ledger = await sp_ledger(app_sessions, org.org_id)
    assert ledger[f"sp_review:5:{lead}"] == 0.25
    assert f"sp_review:5:{peer}" not in ledger
    assert peer_login in fake_claude.runs[0].prompt


async def test_one_dev_and_one_reviewer_never_run_the_agent(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    org = await seed_org(app_sessions)
    dev = await seed_member(app_sessions, org.org_id, "dev")
    peer = await _reviewer(app_sessions, org.org_id, "peer", "developer")
    reviews = [_review(_login("peer", peer))]
    bud_id = await new_bud(app_sessions, org.org_id, number=6, reviews=reviews)
    await add_todo(app_sessions, org.org_id, bud_id, dev, "Build export", sequence=1)

    await run_close_step(app_sessions, org.org_id, bud_id, award_developer_sp_on_close)

    ledger = await sp_ledger(app_sessions, org.org_id)
    assert fake_claude.runs == []
    assert ledger == {f"sp_bud_shipped:6:{dev}": 1.0, f"sp_review:6:{peer}": 0.25}


async def test_reviewing_your_own_bud_earns_no_review_points(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    org = await seed_org(app_sessions)
    dev = await _reviewer(app_sessions, org.org_id, "dev", "developer")
    bud_id = await new_bud(
        app_sessions, org.org_id, number=8, reviews=[_review(_login("dev", dev))]
    )
    await add_todo(app_sessions, org.org_id, bud_id, dev, "Build export", sequence=1)

    await run_close_step(app_sessions, org.org_id, bud_id, award_developer_sp_on_close)

    assert await sp_ledger(app_sessions, org.org_id) == {f"sp_bud_shipped:8:{dev}": 1.0}


async def test_review_pay_is_role_gated_once_and_a_roleless_member_counts_as_developer(
    app_sessions: Factory,
) -> None:
    org = await seed_org(app_sessions)
    people = {
        name: await _reviewer(app_sessions, org.org_id, name, role)
        for name, role in [("dev", "developer"), ("pm", "pm"), ("qa", "qa"), ("nobody", None)]
    }
    reviews = [_review(_login(n, uid)) for n, uid in people.items()]
    reviews += [_review("stranger-login"), _review(_login("pm", people["pm"]), "   ")]
    bud_id = await new_bud(app_sessions, org.org_id, number=9, reviews=reviews)

    async def award(factory: Factory) -> int:
        async with factory() as db:
            bud = await db.get(BUDDocument, bud_id)
            assert bud is not None
            count = await award_code_review_sp(db, org.org_id, bud, {}, exclude_user_ids=set())
            await db.commit()
            return count

    assert await award(app_sessions) == 2
    assert await award(app_sessions) == 0
    assert await sp_ledger(app_sessions, org.org_id) == {
        f"sp_review:9:{people['dev']}": 0.25,
        f"sp_review:9:{people['nobody']}": 0.25,
    }
