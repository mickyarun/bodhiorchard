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

"""Quiz draft generation with the agent run scripted: good, bad and leaky batches."""

from __future__ import annotations

import pytest

from app.models.quiz_question import QuizQuestionStatus
from app.schemas.jobs import JobState
from app.services.quiz_prompt import QUIZ_MODEL
from tests.fakes.app_state import EventRecorder
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
from tests.integration.gamification_fakes.quiz_fake_support import add_question

pytestmark = pytest.mark.integration


@pytest.fixture
def jobs(monkeypatch: pytest.MonkeyPatch) -> JobRecorder:
    """Capture the handler's job-status updates."""
    recorder = JobRecorder()
    recorder.install(monkeypatch)
    return recorder


async def test_a_good_batch_lands_as_drafts_for_review_and_announces_itself(
    app_sessions: Factory,
    fake_claude: FakeClaudeRunner,
    jobs: JobRecorder,
    event_recorder: EventRecorder,
) -> None:
    org = await seed_org(app_sessions)
    await add_question(
        app_sessions, org.org_id, QuizQuestionStatus.DRAFT, prompt="Pending: who owns billing?"
    )
    questions = [
        mcq("queue-store"),
        scramble("cache-name", "sdrie", "redis", "Unscramble our cache layer"),
        fill("db-name", "Our main database is ____.", "postgres"),
    ]
    fake_claude.enqueue(AgentScript.ok(batch(*questions)))

    job_id = await run_batch(org.org_id)
    await event_recorder.settle()

    rows = [q for q in await drafts(app_sessions, org.org_id) if q.generation_job_id == job_id]
    assert sorted(q.question_type.value for q in rows) == [
        "fill_blank",
        "multiple_choice",
        "scramble",
    ]
    assert {q.status for q in rows} == {QuizQuestionStatus.DRAFT}
    assert jobs.final_state == JobState.COMPLETED
    assert event_recorder.payloads(f"quiz:{org.org_id}") == [
        {"event_type": "drafts_ready", "count": 3}
    ]
    (run,) = fake_claude.runs
    assert run.flag("--model") == QUIZ_MODEL
    assert "Pending: who owns billing?" in run.prompt


@pytest.mark.parametrize(
    "output",
    ["Here are your questions: [oops", '{"questions": "none today"}', ""],
    ids=["not-json", "wrong-shape", "empty"],
)
async def test_unparseable_output_inserts_nothing_and_completes_quietly(
    app_sessions: Factory, fake_claude: FakeClaudeRunner, jobs: JobRecorder, output: str
) -> None:
    org = await seed_org(app_sessions)
    fake_claude.enqueue(AgentScript.malformed(output) if output else AgentScript.ok(""))

    await run_batch(org.org_id)

    assert await drafts(app_sessions, org.org_id) == []
    assert jobs.final_state == JobState.COMPLETED


async def test_too_few_questions_keeps_what_came_back_without_a_retry(
    app_sessions: Factory, fake_claude: FakeClaudeRunner, jobs: JobRecorder
) -> None:
    org = await seed_org(app_sessions)
    fake_claude.enqueue(AgentScript.ok(batch(mcq("only-one"))))

    await run_batch(org.org_id, count=5)

    assert len(await drafts(app_sessions, org.org_id)) == 1
    assert len(fake_claude.runs) == 1


async def test_duplicates_within_the_batch_and_against_the_pool_are_dropped(
    app_sessions: Factory, fake_claude: FakeClaudeRunner, jobs: JobRecorder
) -> None:
    org = await seed_org(app_sessions)
    await add_question(app_sessions, org.org_id, QuizQuestionStatus.APPROVED, topic="old-topic")
    questions = [
        mcq("Fresh Topic", "First phrasing?"),
        mcq("  fresh   topic ", "Same topic, other phrasing?"),
        mcq("OLD-TOPIC", "Approved last week?"),
        mcq("another-topic", "Genuinely new?"),
    ]
    fake_claude.enqueue(AgentScript.ok(batch(*questions)))

    await run_batch(org.org_id, count=4)

    new = [q.prompt for q in await drafts(app_sessions, org.org_id) if q.generation_job_id]
    assert sorted(new) == ["First phrasing?", "Genuinely new?"]


async def test_inconsistent_items_are_dropped_and_the_rest_kept(
    app_sessions: Factory, fake_claude: FakeClaudeRunner, jobs: JobRecorder
) -> None:
    org = await seed_org(app_sessions)
    bad_index = {**mcq("bad-index"), "answer_key": {"correct_index": 9}}
    no_topic = {**mcq("x"), "topic_key": ""}
    not_a_rearrangement = scramble("bad-scramble", "xyz", "redis", "Unscramble it")
    questions = [bad_index, no_topic, not_a_rearrangement, "not an object", mcq("good")]
    fake_claude.enqueue(AgentScript.ok(batch(*questions)))

    await run_batch(org.org_id, count=5)

    assert [q.prompt for q in await drafts(app_sessions, org.org_id)] == [mcq("good")["prompt"]]


@pytest.mark.parametrize(
    ("script", "error_code"),
    [(AgentScript.crash(2, "boom"), "unknown"), (AgentScript.max_turns(), "max_turns")],
    ids=["crash", "max-turns"],
)
async def test_a_failed_agent_run_fails_the_job_and_writes_nothing(
    app_sessions: Factory,
    fake_claude: FakeClaudeRunner,
    jobs: JobRecorder,
    script: AgentScript,
    error_code: str,
) -> None:
    org = await seed_org(app_sessions)
    fake_claude.enqueue(script)

    await run_batch(org.org_id)

    assert await drafts(app_sessions, org.org_id) == []
    assert jobs.final_state == JobState.FAILED
    assert jobs.updates[-1]["error_code"] == error_code
