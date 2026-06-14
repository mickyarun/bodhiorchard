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

Once a month is over, its top scorer per org earns SP via the shared
``award_sp`` path. Guards:

- **Idempotent + catch-up**: the award is keyed on a month ``source_ref`` and
  attempted on EVERY daily tick (not just the 1st), so it's granted exactly once
  but still lands even if the process was down on the 1st.
- **No zero-point champion**: a member who only answered (and got everything
  wrong) never wins — the winner must have > 0 points.
- **Active winner only**: if the top scorer left the org, the award rolls to the
  next eligible scorer.
- **Ties split the prize**: meaningful tie-breaks (more-correct, then faster)
  decide a single winner; if people are still genuinely tied on points + correct
  + speed, the SP is split equally among them rather than picked by name.
- **XP is never touched.**
"""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

import structlog

from app.database import AsyncSessionLocal
from app.repositories.organization import OrganizationRepository
from app.repositories.quiz_score import MonthlyLeaderboardRow, QuizScoreRepository
from app.repositories.user import UserRepository
from app.services.org_settings import get_quiz_settings
from app.services.quiz_schedule_math import previous_month_key
from app.services.sp_service import award_sp

logger = structlog.get_logger(__name__)

CHECK_SECONDS = 24 * 60 * 60
RETRY_SLEEP_SECONDS = 60 * 60
ALERT_AFTER_CONSECUTIVE_FAILURES = 2
WINNER_CANDIDATES = 10


def select_winners(
    rows: list[MonthlyLeaderboardRow], active_user_ids: set[uuid.UUID]
) -> list[uuid.UUID]:
    """Pick the winning user id(s) from points-desc leaderboard rows.

    Considers only active members with > 0 points; takes the best
    (points, correct, speed) tuple and returns EVERY active member sharing it —
    so a genuine tie returns multiple winners (the prize is then split), and
    name is never the decider. Pure / testable.
    """
    eligible = [r for r in rows if r.total_points > 0 and r.user_id in active_user_ids]
    if not eligible:
        return []
    top = eligible[0]  # rows arrive points-desc, correct-desc, time-asc
    key = (top.total_points, top.correct_count, top.total_time_ms)
    return [
        r.user_id for r in eligible if (r.total_points, r.correct_count, r.total_time_ms) == key
    ]


async def finalize_org_month(org_id: uuid.UUID, *, period_month: str, amount: float) -> int:
    """Award SP to the previous month's champion(s) for one org. Returns #awards.

    Idempotent (per-user month-keyed source_ref), so it is safe to call every day
    — repeats are no-ops and a missed 1st self-heals. A genuine tie splits the
    prize equally.
    """
    if amount <= 0:
        return 0

    async with AsyncSessionLocal() as db:
        score_repo = QuizScoreRepository(db, org_id=org_id)
        rows = await score_repo.leaderboard(period_month=period_month, limit=WINNER_CANDIDATES)
        if not rows:
            return 0

        user_repo = UserRepository(db)
        active_ids: set[uuid.UUID] = set()
        for row in rows:
            user = await user_repo.get_by_id_in_org(row.user_id, org_id)
            if user and user.is_active:
                active_ids.add(row.user_id)

        winners = select_winners(rows, active_ids)
        if not winners:
            return 0

        share = round(amount / len(winners), 2)
        awarded = 0
        for winner_id in winners:
            result = await award_sp(
                db,
                user_id=winner_id,
                org_id=org_id,
                amount=share,
                source="sp_quiz_monthly_top",
                source_ref=f"sp_quiz_monthly:{org_id}:{period_month}:{winner_id}",
            )
            if result is not None:
                awarded += 1
        await db.commit()

    if awarded:
        logger.info(
            "quiz_monthly_award",
            org_id=str(org_id),
            period=period_month,
            winners=len(winners),
            share=share,
        )
    return awarded


async def sweep_once() -> int:
    """Ensure last month's champion is awarded for every enabled org. Returns count.

    Run daily; the per-month ``source_ref`` makes repeat runs no-ops, so this both
    grants the award and catches up if a prior 1st-of-month run was missed.
    """
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
            awarded += await finalize_org_month(
                org_id, period_month=period_month, amount=settings.monthly_sp_amount
            )
        except Exception:
            logger.warning("quiz_monthly_rollup_org_failed", org_id=str(org_id), exc_info=True)
    return awarded


async def run_forever() -> None:
    """Daily loop — ensures the prior month's champion is awarded (idempotent)."""
    consecutive_failures = 0
    while True:
        try:
            await sweep_once()
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
