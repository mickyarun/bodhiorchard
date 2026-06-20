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

"""Developer quality reward + over-threshold bug penalty at BUD close.

Two complementary outcomes, judged against the same per-complexity bug
threshold:

* **Quality (+):** when QA raised no more than the threshold bugs AND the
  work shipped on or under its first development estimate, every developer
  who did the work earns a quality bonus.
* **Over-threshold (−):** when QA raised more than the threshold, the same
  developers take a small deduction.

The bug count excludes rejected (false-positive) bugs, and "on time" is
measured against the development-phase drift in the post-close metrics
envelope (anchored to the first development estimate, not re-estimates).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.repositories.bug import BugRepository
from app.repositories.feature_learning import FeatureLearningRepository
from app.services.org_settings import get_bug_threshold
from app.services.phase_timing import phase_drift_on_time
from app.services.sp_rules import SP_DEV_BUG_TESTING, SP_DEV_QUALITY_HIGH
from app.services.sp_service import award_sp, penalize_sp

logger = structlog.get_logger(__name__)


async def _development_on_time(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> bool:
    """True when development finished on or under its first estimate."""
    learning = await FeatureLearningRepository(db, org_id=org_id).get_for_bud(bud.id)
    return phase_drift_on_time(learning, "development")


async def award_quality_and_threshold_sp(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    dev_recipients: set[uuid.UUID],
    *,
    org_config: dict[str, Any] | None,
) -> None:
    """Apply the quality bonus or the over-threshold penalty to developers."""
    if not dev_recipients:
        return

    threshold = get_bug_threshold(org_config, bud.complexity)
    bug_count = await BugRepository(db, org_id=org_id).count_valid_testing_bugs_for_bud(bud.id)

    if bug_count > threshold:
        for user_id in dev_recipients:
            await penalize_sp(
                db,
                user_id=user_id,
                org_id=org_id,
                amount=abs(SP_DEV_BUG_TESTING),
                source="sp_bug_over_threshold",
                source_ref=f"sp_bug_threshold:{bud.bud_number}:{user_id}",
            )
        logger.info(
            "sp_bug_over_threshold",
            bud_number=bud.bud_number,
            bug_count=bug_count,
            threshold=threshold,
            developers=len(dev_recipients),
        )
        return

    if await _development_on_time(db, org_id, bud):
        for user_id in dev_recipients:
            await award_sp(
                db,
                user_id=user_id,
                org_id=org_id,
                amount=SP_DEV_QUALITY_HIGH,
                source="sp_quality",
                source_ref=f"sp_quality:{bud.bud_number}:{user_id}",
            )
        logger.info(
            "sp_quality_awarded",
            bud_number=bud.bud_number,
            bug_count=bug_count,
            threshold=threshold,
            developers=len(dev_recipients),
        )
