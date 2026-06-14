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

"""Monthly quiz champion → SP award. The feature's ONLY economy touchpoint.

On the 1st of each month, the previous month's top scorer per org earns SP via
the shared ``award_sp`` path (idempotent on a month-keyed ``source_ref``). XP is
never touched. The winner must still be an active member; if the top scorer has
left, the award rolls to the next eligible scorer.
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.repositories.quiz_score import QuizScoreRepository
from app.repositories.user import UserRepository
from app.services.org_settings import get_quiz_settings
from app.services.quiz_schedule_math import previous_month_key
from app.services.sp_service import award_sp

logger = structlog.get_logger(__name__)

CHECK_SECONDS = 24 * 60 * 60
RETRY_SLEEP_SECONDS = 60 * 60
ALERT_AFTER_CONSECUTIVE_FAILURES = 2
WINNER_CANDIDATES = 5


async def finalize_org_month(org_id: uuid.UUID, *, period_month: str, amount: float) -> bool:
    """Award SP to the previous month's top active scorer for one org.

    Returns True if an award was made. Idempotent: the month-keyed source_ref
    means re-running on the 1st never double-awards.
    """
    if amount <= 0:
        return False

    async with AsyncSessionLocal() as db:
        score_repo = QuizScoreRepository(db, org_id=org_id)
        rows = await score_repo.leaderboard(period_month=period_month, limit=WINNER_CANDIDATES)
        if not rows:
            return False

        user_repo = UserRepository(db)
        winner_id: uuid.UUID | None = None
        for row in rows:
            user = await user_repo.get_by_id_in_org(row.user_id, org_id)
            if user and user.is_active:
                winner_id = row.user_id
                break
        if winner_id is None:
            return False

        awarded = await award_sp(
            db,
            user_id=winner_id,
            org_id=org_id,
            amount=amount,
            source="sp_quiz_monthly_top",
            source_ref=f"sp_quiz_monthly:{org_id}:{period_month}",
        )
        await db.commit()

    if awarded is not None:
        logger.info(
            "quiz_monthly_award", org_id=str(org_id), period=period_month, user_id=str(winner_id)
        )
        return True
    return False


async def sweep_once(today_month_first: bool) -> int:
    """Award the previous month's champion for every enabled org. Returns count."""
    if not today_month_first:
        return 0

    period_month = previous_month_key(datetime.now(UTC).date())
    async with AsyncSessionLocal() as session:
        org_ids = await OrganizationRepository(session).list_all_ids()

    awarded = 0
    for org_id in org_ids:
        try:
            async with AsyncSessionLocal() as cfg_db:
                config = await OrganizationRepository(cfg_db).get_config(org_id)
            settings = get_quiz_settings(config)
            if not settings.enabled:
                continue
            if await finalize_org_month(
                org_id, period_month=period_month, amount=settings.monthly_sp_amount
            ):
                awarded += 1
        except Exception:
            logger.warning("quiz_monthly_rollup_org_failed", org_id=str(org_id), exc_info=True)
    return awarded


async def run_forever() -> None:
    """Daily loop — finalizes the prior month's champion on the 1st."""
    consecutive_failures = 0
    while True:
        try:
            await sweep_once(datetime.now(UTC).day == 1)
            consecutive_failures = 0
            sleep_for = CHECK_SECONDS
        except asyncio.CancelledError:
            raise
        except Exception:
            consecutive_failures += 1
            log = (
                logger.error
                if consecutive_failures >= ALERT_AFTER_CONSECUTIVE_FAILURES
                else logger.exception
            )
            log("quiz_monthly_rollup_failed", consecutive_failures=consecutive_failures)
            sleep_for = RETRY_SLEEP_SECONDS
        await asyncio.sleep(sleep_for)
