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

"""Quiz batch generation — the agent job handler + the rolling top-up loop.

Generation is OFF the player-facing hot path: a daily sweep keeps each org's
review queue (DRAFT + APPROVED) topped up to a small rolling buffer ahead of
time, so admins always have questions to approve before a quiz day arrives. The
job handler runs the generation agent and persists results as DRAFTs for review.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import structlog

from app.database import AsyncSessionLocal
from app.models.quiz_question import QuizQuestionStatus
from app.repositories.organization import OrganizationRepository
from app.repositories.quiz_question import QuizQuestionRepository
from app.repositories.quiz_topic_history import QuizTopicHistoryRepository
from app.schemas.jobs import JobState
from app.schemas.quiz import QuizBatchJobPayload
from app.services.claude_runner import NO_REPO_CONTEXT, ClaudeRunnerConfig, run_claude_code
from app.services.event_bus import publish
from app.services.job_queue import JOB_QUIZ_BATCH, create_job, update_job
from app.services.job_utils import build_mcp_config, make_progress_callback
from app.services.org_settings import get_quiz_settings
from app.services.quiz_persist import persist_generated_batch
from app.services.quiz_prompt import QUIZ_MCP_TOOLS, QUIZ_MODEL, build_batch_prompt

logger = structlog.get_logger(__name__)

SLEEP_SECONDS = 24 * 60 * 60
RETRY_SLEEP_SECONDS = 60 * 60
ALERT_AFTER_CONSECUTIVE_FAILURES = 2
DENYLIST_WINDOW_DAYS = 60
# Buffer kept on top of "one per active quiz day" so admins always have spare
# questions to approve even after rejecting a few.
POOL_BUFFER = 2
GENERATION_TIMEOUT_SECONDS = 300
GENERATION_MAX_TURNS = 30


async def handle_quiz_batch_job(job_id: str, raw_payload: dict[str, Any]) -> None:
    """Run the generation agent for one org and persist drafts for review."""
    payload = QuizBatchJobPayload(**raw_payload)
    org_id = uuid.UUID(payload.org_id)
    update_job(job_id, status_message="Generating quiz drafts...", progress_pct=10)

    async with AsyncSessionLocal() as db:
        try:
            since = datetime.now(UTC).date() - timedelta(days=DENYLIST_WINDOW_DAYS)
            history_repo = QuizTopicHistoryRepository(db, org_id=org_id)
            question_repo = QuizQuestionRepository(db, org_id=org_id)
            denylist = await history_repo.recent_labels(since=since, limit=60)
            denylist += await question_repo.pending_topic_labels(limit=40)

            prompt = build_batch_prompt(
                count=payload.count,
                difficulty=payload.difficulty,
                enabled_types=payload.enabled_types,
                denylist=denylist,
            )
            mcp = build_mcp_config(org_id=str(org_id), tool_names=QUIZ_MCP_TOOLS)
            config = ClaudeRunnerConfig(
                max_turns=GENERATION_MAX_TURNS,
                timeout_seconds=GENERATION_TIMEOUT_SECONDS,
                mcp=mcp,
                model=QUIZ_MODEL,
                output_format="json",
            )
            update_job(job_id, status_message="Running quiz agent...", progress_pct=30)
            result = await run_claude_code(
                prompt=prompt,
                working_dir=NO_REPO_CONTEXT,
                config=config,
                progress_callback=make_progress_callback(job_id),
            )
            if not result.success:
                update_job(
                    job_id,
                    state=JobState.FAILED,
                    error=result.error or "Quiz generation failed",
                    error_code=result.error_code,
                )
                return

            inserted = await persist_generated_batch(
                db,
                org_id=org_id,
                raw_output=result.output or "",
                generation_job_id=job_id,
            )
            await db.commit()
            publish(f"quiz:{org_id}", {"event_type": "drafts_ready", "count": inserted})
        except Exception:
            await db.rollback()
            logger.exception("quiz_batch_job_failed", org_id=str(org_id), job_id=job_id)
            update_job(job_id, state=JobState.FAILED, error="Quiz generation crashed")
            return

    update_job(job_id, state=JobState.COMPLETED, status_message="Done", progress_pct=100)


async def _topup_org(org_id: uuid.UUID) -> int:
    """Enqueue a generation batch if the org's review pool is below target.

    Returns the number of questions requested (0 when already stocked or disabled).
    """
    async with AsyncSessionLocal() as db:
        config = await OrganizationRepository(db).get_config(org_id)
        settings = get_quiz_settings(config)
        if not settings.enabled:
            return 0

        repo = QuizQuestionRepository(db, org_id=org_id)
        pending = await repo.count_by_status(QuizQuestionStatus.DRAFT)
        pending += await repo.count_by_status(QuizQuestionStatus.APPROVED)

    target = len(settings.active_weekdays) + POOL_BUFFER
    needed = target - pending
    if needed <= 0:
        return 0

    create_job(
        JOB_QUIZ_BATCH,
        payload=QuizBatchJobPayload(
            org_id=str(org_id),
            count=needed,
            difficulty=settings.difficulty,
            enabled_types=settings.enabled_question_types,
        ).model_dump(mode="json"),
    )
    logger.info("quiz_batch_topup_enqueued", org_id=str(org_id), count=needed)
    return needed


async def sweep_once() -> int:
    """Top up every org's review pool once. Returns total questions requested."""
    async with AsyncSessionLocal() as session:
        org_ids = await OrganizationRepository(session).list_all_ids()

    total = 0
    for oid in org_ids:
        try:
            total += await _topup_org(oid)
        except Exception:
            logger.warning("quiz_batch_topup_org_failed", org_id=str(oid), exc_info=True)
    return total


async def run_forever() -> None:
    """Daily loop — keeps every org's review queue stocked ahead of quiz days."""
    consecutive_failures = 0
    while True:
        try:
            await sweep_once()
            consecutive_failures = 0
            sleep_for = SLEEP_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_failures += 1
            log = (
                logger.error
                if consecutive_failures >= ALERT_AFTER_CONSECUTIVE_FAILURES
                else logger.exception
            )
            log("quiz_batch_sweep_failed", consecutive_failures=consecutive_failures)
            sleep_for = RETRY_SLEEP_SECONDS
        await asyncio.sleep(sleep_for)
