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

"""Parse, validate, and persist an agent-generated quiz batch as DRAFTs.

Failures here are invisible to employees — they only affect the review queue, so
the policy is "keep every good question, drop the rest, never crash". A draft is
dropped when it is malformed, content-inconsistent (handled by the Pydantic
validator), or duplicates a topic already in history, the pending pool, or this
same batch. Topics are recorded in history only on approval/use — not here — so
a rejected draft never burns a topic.
"""

from __future__ import annotations

import uuid

import structlog
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.quiz_question import QuizQuestionRepository
from app.repositories.quiz_topic_history import QuizTopicHistoryRepository
from app.schemas.quiz import GeneratedQuestion
from app.services.json_parser import parse_json_response
from app.services.quiz_content import topic_hash

logger = structlog.get_logger(__name__)


async def persist_generated_batch(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    raw_output: str,
    generation_job_id: str | None,
) -> int:
    """Persist valid, non-duplicate questions from ``raw_output`` as DRAFTs.

    Returns the number actually inserted.
    """
    parsed = parse_json_response(raw_output)
    if not parsed or not isinstance(parsed.get("questions"), list):
        logger.warning("quiz_batch_unparseable", org_id=str(org_id))
        return 0

    question_repo = QuizQuestionRepository(db, org_id=org_id)
    history_repo = QuizTopicHistoryRepository(db, org_id=org_id)

    # Validate each question independently so one bad item never drops the batch.
    valid: list[tuple[GeneratedQuestion, str]] = []
    for raw in parsed["questions"]:
        try:
            question = GeneratedQuestion(**raw)
        except (ValidationError, TypeError) as exc:
            logger.info("quiz_question_invalid", org_id=str(org_id), error=str(exc)[:200])
            continue
        valid.append((question, topic_hash(question.topic_key)))

    if not valid:
        return 0

    # Hard non-repeat: drop against history, the pending pool, and within-batch.
    candidate_hashes = [h for _, h in valid]
    seen = await history_repo.existing_hashes(candidate_hashes)
    seen |= await question_repo.pending_topic_hashes()

    inserted = 0
    for question, t_hash in valid:
        if t_hash in seen:
            continue
        seen.add(t_hash)  # also dedupe within this batch
        await question_repo.add_draft(
            question_type=question.question_type,
            difficulty=question.difficulty,
            prompt=question.prompt,
            payload=question.payload,
            answer_key=question.answer_key,
            explanation=question.explanation,
            category=question.category,
            topic_hash=t_hash,
            source_refs=question.source_refs,
            generation_job_id=generation_job_id,
        )
        inserted += 1

    logger.info(
        "quiz_batch_persisted",
        org_id=str(org_id),
        valid=len(valid),
        inserted=inserted,
        dropped=len(valid) - inserted,
    )
    return inserted
