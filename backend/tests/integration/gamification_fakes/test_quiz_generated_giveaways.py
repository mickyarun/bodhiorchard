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

"""A generated question must not print its own answer in what players see.

The prompt and the payload (scrambled letters, fill-blank hint) are shown while
the quiz is open; only ``answer_key`` is withheld. A draft that repeats the
answer there is a giveaway and should never reach the review queue.
"""

from __future__ import annotations

import pytest

from tests.fakes.claude_runner import FakeClaudeRunner
from tests.fakes.claude_script import AgentScript
from tests.fakes.seed import Factory, seed_org
from tests.integration.gamification_fakes.quiz_batch_support import (
    JobRecorder,
    batch,
    drafts,
    fill,
    mcq,
    run_batch,
    scramble,
)

pytestmark = pytest.mark.integration

CLEAN = mcq("clean", "Which store backs the job queue?")


@pytest.fixture(autouse=True)
def jobs(monkeypatch: pytest.MonkeyPatch) -> JobRecorder:
    """Capture the handler's job-status updates."""
    recorder = JobRecorder()
    recorder.install(monkeypatch)
    return recorder


@pytest.mark.parametrize(
    "leaky",
    [
        scramble("same", "Redis", "redis", "Unscramble our cache layer"),
        scramble("named", "sdire", "redis", "Unscramble Redis, the cache layer"),
        fill("in-prompt", "Postgres is the ____ behind every service.", "Postgres"),
        fill("in-hint", "Our main database is ____.", "postgres", hint="starts with Postgres"),
    ],
    ids=["scramble-not-scrambled", "scramble-named-in-prompt", "fill-in-prompt", "fill-in-hint"],
)
async def test_a_draft_that_shows_its_answer_is_dropped(
    app_sessions: Factory, fake_claude: FakeClaudeRunner, leaky: dict[str, object]
) -> None:
    org = await seed_org(app_sessions)
    fake_claude.enqueue(AgentScript.ok(batch(leaky, CLEAN)))

    await run_batch(org.org_id, count=2)

    assert [q.prompt for q in await drafts(app_sessions, org.org_id)] == [CLEAN["prompt"]]


async def test_an_answer_that_only_appears_inside_a_longer_word_is_not_a_giveaway(
    app_sessions: Factory, fake_claude: FakeClaudeRunner
) -> None:
    org = await seed_org(app_sessions)
    subtle = fill("lang", "The ____ toolchain keeps going strong in our CLI.", "Go")
    fake_claude.enqueue(AgentScript.ok(batch(subtle)))

    await run_batch(org.org_id, count=1)

    assert [q.prompt for q in await drafts(app_sessions, org.org_id)] == [subtle["prompt"]]
