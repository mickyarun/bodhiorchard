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

"""Reveal one quiz and fold its answers into the monthly totals (no XP, ever).

Points only reach the monthly board here, after the window has closed. Scoring
at submit time would move the board the moment someone answered correctly,
which tells everyone watching it who was right before the reveal.

The flip and the fold run in the caller's transaction, and the fold is guarded
twice: only the caller that wins the OPEN→REVEALED flip folds, and each answer
is claimed through its ``scored_at`` marker, so a repeated or concurrent reveal
pass never counts an answer twice. Answers whose ``scored_at`` was already set
(those scored at submit time before this rule existed) are left alone.
SQL stays in the repositories; this module only orchestrates them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.quiz import QuizRepository
from app.repositories.quiz_answer import QuizAnswerRepository
from app.repositories.quiz_score import QuizScoreRepository
from app.services.quiz_schedule_math import current_month_key


async def reveal_quiz(
    db: AsyncSession, *, org_id: uuid.UUID, quiz_id: uuid.UUID, quiz_date: date
) -> bool:
    """Flip a closed quiz to REVEALED and fold its answers into the monthly totals.

    Returns True only for the caller that won the flip. The caller commits, so
    the flip and the fold land together or not at all.
    """
    if not await QuizRepository(db, org_id=org_id).flip_to_revealed(quiz_id):
        return False
    await _fold_answers(db, org_id=org_id, quiz_id=quiz_id, quiz_date=quiz_date)
    return True


async def _fold_answers(
    db: AsyncSession, *, org_id: uuid.UUID, quiz_id: uuid.UUID, quiz_date: date
) -> int:
    """Add a revealed quiz's unscored answers to each player's month. Returns #folded."""
    claimed = await QuizAnswerRepository(db, org_id=org_id).claim_unscored(
        quiz_id=quiz_id, scored_at=datetime.now(UTC)
    )
    if not claimed:
        return 0

    prev = await QuizRepository(db, org_id=org_id).previous_quiz_with_question(quiz_date)
    prev_quiz_date = prev[0].quiz_date if prev else None
    score_repo = QuizScoreRepository(db, org_id=org_id)
    seen: set[uuid.UUID] = set()
    for answer in claimed:
        await score_repo.record(
            user_id=answer.user_id,
            # Points belong to the month the quiz ran in, not the reveal month.
            period_month=current_month_key(quiz_date),
            quiz_date=quiz_date,
            prev_quiz_date=prev_quiz_date,
            is_correct=answer.is_correct,
            points=answer.points,
            latency_ms=answer.latency_ms,
            new_quiz_participation=answer.user_id not in seen,
        )
        seen.add(answer.user_id)
    return len(claimed)
