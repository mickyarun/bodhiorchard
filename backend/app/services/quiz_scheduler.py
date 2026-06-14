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

"""Quiz scheduler — opens approved questions on schedule and reveals on close.

Generation is NOT on this path (that's the batch top-up loop). This loop ticks
every 60s and, per org, (1) opens the next APPROVED question when the local
fire time on an active weekday is reached, and (2) flips windows closed to
REVEALED. The 60s tick recomputes local fire times each pass, so it is naturally
DST-correct and self-heals after a restart; all durable state lives in Postgres.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.exc import IntegrityError

from app.database import AsyncSessionLocal
from app.models.quiz_question import QuizQuestionStatus
from app.repositories.organization import OrganizationRepository
from app.repositories.quiz import QuizRepository
from app.repositories.quiz_question import QuizQuestionRepository
from app.schemas.settings import QuizGameSettings
from app.services.event_bus import publish
from app.services.org_settings import get_quiz_settings
from app.services.quiz_notify import notify_quiz_open, notify_quiz_reveal, nudge_low_queue
from app.services.quiz_schedule_math import compute_open_window, resolve_zone

logger = structlog.get_logger(__name__)

TICK_SECONDS = 60
RETRY_SLEEP_SECONDS = 60
ALERT_AFTER_CONSECUTIVE_FAILURES = 3


class _NoApprovedQuestionError(Exception):
    """Internal signal: nothing approved is available to open today."""


async def _open_pass(org_id: uuid.UUID, settings: QuizGameSettings, now_utc: datetime) -> None:
    """Open today's quiz from the approved pool if it's fire time and none exists."""
    window = compute_open_window(
        now_utc=now_utc,
        zone=resolve_zone(settings.timezone),
        quiz_time=settings.quiz_time,
        active_weekdays=settings.active_weekdays,
        window_minutes=settings.window_minutes,
    )
    if window is None:
        return

    async with AsyncSessionLocal() as db:
        quiz_repo = QuizRepository(db, org_id=org_id)
        if await quiz_repo.exists_for_date(window.quiz_date):
            return

        question_repo = QuizQuestionRepository(db, org_id=org_id)
        prev = await quiz_repo.previous_quiz_with_question(window.quiz_date)
        exclude_type = prev[1].question_type if prev else None

        try:
            async with db.begin_nested():
                question = await question_repo.claim_next_approved(
                    today=window.quiz_date, exclude_type=exclude_type
                )
                if question is None:
                    raise _NoApprovedQuestionError
                await quiz_repo.create(
                    question_id=question.id,
                    quiz_date=window.quiz_date,
                    open_at=window.open_at,
                    reveal_at=window.reveal_at,
                )
            await db.commit()
        except _NoApprovedQuestionError:
            await db.rollback()
            remaining = await QuizQuestionRepository(db, org_id=org_id).count_by_status(
                QuizQuestionStatus.APPROVED
            )
            logger.info("quiz_open_skipped_empty_queue", org_id=str(org_id))
            nudge_low_queue(org_id, approved_remaining=remaining)
            return
        except IntegrityError:
            # Another instance opened this org-day first (uq_quizzes_org_date).
            await db.rollback()
            return

    publish(f"quiz:{org_id}", {"event_type": "quiz_opened"})
    if settings.slack_notify_open:
        await notify_quiz_open(org_id)


async def _reveal_pass(org_id: uuid.UUID, settings: QuizGameSettings, now_utc: datetime) -> None:
    """Flip any closed-window OPEN quizzes to REVEALED (exactly-once per quiz)."""
    async with AsyncSessionLocal() as db:
        quiz_repo = QuizRepository(db, org_id=org_id)
        due = await quiz_repo.list_open_past_reveal(now_utc)
        revealed_ids = []
        for quiz in due:
            if await quiz_repo.flip_to_revealed(quiz.id):
                revealed_ids.append(quiz.id)
        if revealed_ids:
            await db.commit()

    for _quiz_id in revealed_ids:
        publish(f"quiz:{org_id}", {"event_type": "quiz_revealed"})
    # One reveal DM per tick regardless of how many quizzes closed (a multi-day
    # outage could close several at once — don't spam members N identical DMs).
    if revealed_ids and settings.slack_notify_reveal:
        await notify_quiz_reveal(org_id)


async def tick_once() -> None:
    """One scheduler pass over every org: open due quizzes, reveal closed ones."""
    now_utc = datetime.now(UTC)
    async with AsyncSessionLocal() as session:
        org_ids = await OrganizationRepository(session).list_all_ids()

    for org_id in org_ids:
        try:
            async with AsyncSessionLocal() as cfg_db:
                config = await OrganizationRepository(cfg_db).get_config(org_id)
            settings = get_quiz_settings(config)
            if not settings.enabled:
                continue
            await _open_pass(org_id, settings, now_utc)
            await _reveal_pass(org_id, settings, now_utc)
        except Exception:
            logger.warning("quiz_scheduler_org_failed", org_id=str(org_id), exc_info=True)


async def run_forever() -> None:
    """60s tick loop — per-org timezone-aware open/reveal. Single-instance safe."""
    consecutive_failures = 0
    while True:
        try:
            await tick_once()
            consecutive_failures = 0
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_failures += 1
            log = (
                logger.error
                if consecutive_failures >= ALERT_AFTER_CONSECUTIVE_FAILURES
                else logger.exception
            )
            log("quiz_scheduler_tick_failed", consecutive_failures=consecutive_failures)
        await asyncio.sleep(TICK_SECONDS)
