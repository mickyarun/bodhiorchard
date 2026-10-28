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

"""The BUD-shipped SP split, with the substance judge run as a scripted agent.

``award_developer_sp_on_close`` asks the agent CLI to weigh each completed
todo. The fake answers with the JSON (or the garbage) a real run could
produce, and the ledger on Postgres shows who was paid what.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pytest

from app.services.sp_developer import award_developer_sp_on_close
from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.seed import Factory, seed_member, seed_org
from tests.integration.gamification_fakes.ledger_support import sp_ledger
from tests.integration.gamification_fakes.sp_support import (
    add_learning,
    add_todo,
    new_bud,
    run_close_step,
)

pytestmark = pytest.mark.integration

BUD_NUMBER = 41


@dataclass(frozen=True)
class TwoDevBud:
    """An org with one BUD whose work was split between two developers."""

    org_id: uuid.UUID
    bud_id: uuid.UUID
    ana: uuid.UUID
    ben: uuid.UUID
    ana_todo: uuid.UUID
    ben_todo: uuid.UUID


async def _two_dev_bud(factory: Factory) -> TwoDevBud:
    org = await seed_org(factory)
    ana = await seed_member(factory, org.org_id, "ana")
    ben = await seed_member(factory, org.org_id, "ben")
    bud_id = await new_bud(factory, org.org_id, number=BUD_NUMBER)
    ana_todo = await add_todo(factory, org.org_id, bud_id, ana, "Build retry queue", sequence=1)
    ben_todo = await add_todo(factory, org.org_id, bud_id, ben, "Rename a label", sequence=2)
    return TwoDevBud(org.org_id, bud_id, ana, ben, ana_todo, ben_todo)


def _verdict(weights: dict[uuid.UUID | str, object]) -> str:
    return json.dumps({"todo_weights": {str(k): v for k, v in weights.items()}})


async def _close(factory: Factory, bud: TwoDevBud) -> dict[str, float]:
    await run_close_step(factory, bud.org_id, bud.bud_id, award_developer_sp_on_close)
    return await sp_ledger(factory, bud.org_id)


def _shipped(ledger: dict[str, float], user_id: uuid.UUID) -> float | None:
    return ledger.get(f"sp_bud_shipped:{BUD_NUMBER}:{user_id}")


async def test_judge_weights_split_the_pool_and_see_todos_as_untrusted_data(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    bud = await _two_dev_bud(app_sessions)
    fake_claude.enqueue(AgentScript.ok(_verdict({bud.ana_todo: 0.9, bud.ben_todo: 0.3})))

    ledger = await _close(app_sessions, bud)

    assert (_shipped(ledger, bud.ana), _shipped(ledger, bud.ben)) == (0.75, 0.25)
    (run,) = fake_claude.runs
    assert run.flag("--max-turns") == "1"
    untrusted = run.prompt.split("<untrusted_data>\n")[1].split("</untrusted_data>")[0]
    assert "Build retry queue" in untrusted and "Rename a label" in untrusted


async def test_a_todo_judged_trivial_earns_no_share_and_no_quality_bonus(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    bud = await _two_dev_bud(app_sessions)
    await add_learning(app_sessions, bud.org_id, bud.bud_id, drift={"development": -5.0})
    fake_claude.enqueue(AgentScript.ok(_verdict({bud.ana_todo: 1.0, bud.ben_todo: 0.0})))

    ledger = await _close(app_sessions, bud)

    assert _shipped(ledger, bud.ana) == 1.0
    assert ledger[f"sp_quality:{BUD_NUMBER}:{bud.ana}"] == 0.5
    assert not any(str(bud.ben) in ref for ref in ledger)


async def test_out_of_range_weights_are_clamped_and_unknown_ids_ignored(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    bud = await _two_dev_bud(app_sessions)
    verdict = _verdict({bud.ana_todo: 7, bud.ben_todo: -3, uuid.uuid4(): 1.0})
    fake_claude.enqueue(AgentScript.ok(verdict))

    ledger = await _close(app_sessions, bud)

    assert _shipped(ledger, bud.ana) == 1.0
    assert _shipped(ledger, bud.ben) is None


async def test_a_fenced_verdict_after_a_leaked_insight_block_still_parses(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    bud = await _two_dev_bud(app_sessions)
    fenced = "```json\n" + _verdict({bud.ana_todo: 0.25, bud.ben_todo: 0.75}) + "\n```"
    fake_claude.enqueue(AgentScript.ok(fenced).with_insight())

    ledger = await _close(app_sessions, bud)

    assert (_shipped(ledger, bud.ana), _shipped(ledger, bud.ben)) == (0.25, 0.75)


@pytest.mark.parametrize(
    "script",
    [
        AgentScript.malformed("the work all looked substantive to me {"),
        AgentScript.crash(1, "fatal: agent crashed"),
        AgentScript.max_turns(),
        AgentScript.ok('{"todo_weights": "everyone did great"}'),
    ],
    ids=["not-json", "crash", "max-turns", "wrong-shape"],
)
async def test_an_unusable_judge_run_falls_back_to_an_equal_split(
    app_sessions: Factory, fake_claude: FakeClaudeRunner, script: AgentScript
) -> None:
    bud = await _two_dev_bud(app_sessions)
    fake_claude.enqueue(script)

    ledger = await _close(app_sessions, bud)

    assert len(fake_claude.runs) == 1
    assert (_shipped(ledger, bud.ana), _shipped(ledger, bud.ben)) == (0.5, 0.5)


async def test_a_second_close_with_a_different_verdict_pays_nothing_new(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    bud = await _two_dev_bud(app_sessions)
    fake_claude.enqueue(
        AgentScript.ok(_verdict({bud.ana_todo: 1.0, bud.ben_todo: 1.0})),
        AgentScript.ok(_verdict({bud.ana_todo: 1.0, bud.ben_todo: 0.0})),
    )

    first = await _close(app_sessions, bud)
    second = await _close(app_sessions, bud)

    assert second == first
    assert (_shipped(second, bud.ana), _shipped(second, bud.ben)) == (0.5, 0.5)
    assert len(fake_claude.runs) == 2
