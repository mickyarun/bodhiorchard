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

"""PM Skill-Point rules, settled at BUD close.

The PM is identified as the person who first moved the BUD out of the
requirement stage into design (from the timeline). They earn:

* **Requirement → design (+1.0, tapered):** for turning a requirement into
  a designable BUD. The credit tapers with estimate-vs-actual overrun — a
  BUD that ran >30% over its estimate pays half, >50% over pays nothing
  (scope crept / the requirement was under-specified).
* **Tech spec on time (+0.25):** when the tech-arch phase landed within its
  first estimate.

Best-effort and deduped on ``source_ref``; never blocks the close handler.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.feature_learning import FeatureLearning
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.feature_learning import FeatureLearningRepository
from app.services.phase_timing import phase_drift_on_time
from app.services.sp_rules import (
    SP_PM_REQUIREMENT_TO_DESIGN,
    SP_PM_SCOPE_VARIATION_HALF_PCT,
    SP_PM_SCOPE_VARIATION_NONE_PCT,
    SP_PM_TECHSPEC_ON_TIME,
)
from app.services.sp_service import award_sp, get_user_role

logger = structlog.get_logger(__name__)


def _requirement_amount(learning: FeatureLearning | None) -> float:
    """Requirement→design credit, tapered by estimate-vs-actual overrun.

    The taper reads the retro's estimate-vs-actual variance (the overall
    ``cycle_time_days`` vs original ``estimated_days``). No estimate data →
    full credit (we can't dock what we can't measure). Overrun above the NONE
    threshold pays nothing; above HALF pays half; on or under estimate pays
    the full amount.
    """
    base = SP_PM_REQUIREMENT_TO_DESIGN
    if learning is None or not learning.estimated_days or learning.cycle_time_days is None:
        return base
    over_pct = (learning.cycle_time_days - learning.estimated_days) / learning.estimated_days * 100
    if over_pct > SP_PM_SCOPE_VARIATION_NONE_PCT:
        return 0.0
    if over_pct > SP_PM_SCOPE_VARIATION_HALF_PCT:
        return round(base / 2, 2)
    return base


async def award_pm_sp_on_close(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Award the PM (requirement→design mover) their close-time SP.

    Fully guarded so a transient failure in the setup reads (timeline / role /
    metrics) degrades to "no award" rather than breaking the close handler.
    """
    try:
        mover = await BUDTimelineRepository(db, org_id=org_id).first_status_change_to(
            bud.id, BUDStatus.DESIGN.value
        )
        if mover is None or mover[0] is None:
            return
        pm_id = mover[0]
        if await get_user_role(db, pm_id, org_id) != "pm":
            return

        learning = await FeatureLearningRepository(db, org_id=org_id).get_for_bud(bud.id)

        amount = _requirement_amount(learning)
        if amount > 0:
            await award_sp(
                db,
                user_id=pm_id,
                org_id=org_id,
                amount=amount,
                source="sp_pm_requirement",
                source_ref=f"sp_pm_requirement:{bud.bud_number}:{pm_id}",
            )
        if phase_drift_on_time(learning, "tech_arch"):
            await award_sp(
                db,
                user_id=pm_id,
                org_id=org_id,
                amount=SP_PM_TECHSPEC_ON_TIME,
                source="sp_pm_techspec",
                source_ref=f"sp_pm_techspec:{bud.bud_number}:{pm_id}",
            )
    except Exception:
        logger.warning("sp_pm_failed", bud_number=bud.bud_number, exc_info=True)
