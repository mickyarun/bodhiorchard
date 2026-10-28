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

"""Generated-question JSON and a job recorder for the quiz generation tests."""

from __future__ import annotations

import inspect
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
from sqlalchemy import select

from app.models.quiz_question import QuizQuestion
from app.schemas.jobs import JobState
from app.services import job_queue, quiz_batch_generation
from app.services.job_handlers import setup_job_handlers
from app.services.quiz_batch_generation import handle_quiz_batch_job
from tests.fakes.seed import Factory


def mcq(topic: str, prompt: str = "Which store backs the job queue?") -> dict[str, Any]:
    """A valid multiple-choice question."""
    return {
        "question_type": "multiple_choice",
        "prompt": prompt,
        "payload": {"choices": ["Redis", "Kafka", "Postgres", "SQS"]},
        "answer_key": {"correct_index": 0},
        "topic_key": topic,
    }


def scramble(topic: str, scrambled: str, answer: str, prompt: str) -> dict[str, Any]:
    """A scramble question (the caller decides whether it is any good)."""
    return {
        "question_type": "scramble",
        "prompt": prompt,
        "payload": {"scrambled": scrambled, "kind": "letters"},
        "answer_key": {"answer": answer},
        "topic_key": topic,
    }


def fill(topic: str, prompt: str, answer: str, hint: str = "a datastore") -> dict[str, Any]:
    """A fill-the-blank question (the caller decides whether it is any good)."""
    return {
        "question_type": "fill_blank",
        "prompt": prompt,
        "payload": {"hint": hint},
        "answer_key": {"answer": answer, "aliases": []},
        "topic_key": topic,
    }


def batch(*questions: object) -> str:
    """The agent's JSON envelope for a batch."""
    return json.dumps({"questions": list(questions)})


@dataclass(frozen=True)
class CreatedJob:
    """One job the code under test enqueued."""

    job_type: str
    payload: dict[str, Any]


@dataclass
class JobRecorder:
    """Every ``update_job`` the generation handler made, and every job it enqueued.

    Each call is bound against the real ``job_queue`` signature, so a call the
    real queue would reject fails here too, and the quiz job type must be
    registered by the app's own ``setup_job_handlers``.
    """

    updates: list[dict[str, Any]] = field(default_factory=list)
    created: list[CreatedJob] = field(default_factory=list)

    def install(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Record instead of touching the in-memory job store."""
        monkeypatch.setattr(job_queue, "_registry", {})
        setup_job_handlers()
        handler = job_queue._registry[job_queue.JOB_QUIZ_BATCH][0]
        assert handler is handle_quiz_batch_job
        update_sig = inspect.signature(job_queue.update_job)
        create_sig = inspect.signature(job_queue.create_job)

        def update(*args: Any, **kwargs: Any) -> None:
            bound = update_sig.bind(*args, **kwargs)
            self.updates.append(dict(bound.arguments))

        def create(*args: Any, **kwargs: Any) -> None:
            bound = create_sig.bind(*args, **kwargs)
            job = CreatedJob(bound.arguments["job_type"], bound.arguments["payload"])
            self.created.append(job)

        monkeypatch.setattr(quiz_batch_generation, "update_job", update)
        monkeypatch.setattr(quiz_batch_generation, "create_job", create)

    @property
    def final_state(self) -> JobState | None:
        """The last terminal state the handler reported."""
        states = [u["state"] for u in self.updates if u.get("state") is not None]
        return states[-1] if states else None


async def run_batch(org_id: uuid.UUID, count: int = 3) -> str:
    """Run the generation job handler for ``org_id``; return its job id."""
    job_id = f"quiz-{uuid.uuid4().hex[:12]}"
    payload = {"org_id": str(org_id), "count": count, "enabled_types": ["multiple_choice"]}
    await handle_quiz_batch_job(job_id, payload)
    return job_id


async def drafts(factory: Factory, org_id: uuid.UUID) -> list[QuizQuestion]:
    """The org's pooled questions, oldest first."""
    async with factory() as db:
        rows = await db.scalars(
            select(QuizQuestion)
            .where(QuizQuestion.org_id == org_id)
            .order_by(QuizQuestion.created_at, QuizQuestion.prompt)
        )
        return list(rows)
