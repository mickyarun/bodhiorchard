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

"""A question that already ran as a quiz is final in the review queue.

Approving it again would put it back in the pool and replay it (everyone who
answered it before is told "already answered" and its answer was revealed);
editing it would rewrite the reveal and recap of a quiz people already played.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.models.quiz_question import QuizQuestionStatus, QuizQuestionType
from app.schemas.quiz import QuizReviewEdit
from app.services import quiz_review
from app.services.quiz_review import (
    approve_question,
    edit_question,
    reject_question,
)

Action = Callable[[Any, uuid.UUID], Awaitable[Any]]


def _install(monkeypatch: pytest.MonkeyPatch, status: QuizQuestionStatus) -> SimpleNamespace:
    question = SimpleNamespace(
        status=status,
        question_type=QuizQuestionType.MULTIPLE_CHOICE,
        prompt="Which store backs the queue?",
        payload={"choices": ["Redis", "Kafka"]},
        answer_key={"correct_index": 0},
        topic_hash="h",
    )
    repo = SimpleNamespace(
        get_by_id=AsyncMock(return_value=question), set_status=AsyncMock(return_value=question)
    )
    history = SimpleNamespace(upsert=AsyncMock())
    monkeypatch.setattr(quiz_review, "QuizQuestionRepository", lambda db, org_id: repo)
    monkeypatch.setattr(quiz_review, "QuizTopicHistoryRepository", lambda db, org_id: history)
    return repo


async def _approve(db: Any, org_id: uuid.UUID) -> Any:
    return await approve_question(
        db, org_id=org_id, question_id=uuid.uuid4(), approver_id=uuid.uuid4()
    )


async def _reject(db: Any, org_id: uuid.UUID) -> Any:
    return await reject_question(db, org_id=org_id, question_id=uuid.uuid4())


async def _edit(db: Any, org_id: uuid.UUID) -> Any:
    edit = QuizReviewEdit(answer_key={"correct_index": 1})
    return await edit_question(db, org_id=org_id, question_id=uuid.uuid4(), edit=edit)


@pytest.mark.parametrize("action", [_approve, _reject, _edit], ids=["approve", "reject", "edit"])
async def test_a_used_question_cannot_be_reviewed_again(
    monkeypatch: pytest.MonkeyPatch, action: Action
) -> None:
    repo = _install(monkeypatch, QuizQuestionStatus.USED)
    db = AsyncMock()

    with pytest.raises(Exception, match="already ran") as raised:
        await action(db, uuid.uuid4())

    assert type(raised.value).__name__ == "QuizQuestionAlreadyUsedError"

    repo.set_status.assert_not_awaited()
    db.flush.assert_not_awaited()
    question = await repo.get_by_id(uuid.uuid4())
    assert question.answer_key == {"correct_index": 0}


@pytest.mark.parametrize("status", [QuizQuestionStatus.DRAFT, QuizQuestionStatus.REJECTED])
async def test_a_draft_or_rejected_question_can_still_be_approved(
    monkeypatch: pytest.MonkeyPatch, status: QuizQuestionStatus
) -> None:
    repo = _install(monkeypatch, status)

    await _approve(AsyncMock(), uuid.uuid4())

    assert repo.set_status.await_args.kwargs["status"] == QuizQuestionStatus.APPROVED
