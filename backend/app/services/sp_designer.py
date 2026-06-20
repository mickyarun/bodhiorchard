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

"""Designer Skill-Point rules, settled at BUD close.

A designer is anyone who emitted a ``design_updated`` event on the BUD
(figma-link change, design MCP write, or design-section AI chat) AND holds
the ``designer`` role. Each earns:

* **Design contribution (+0.25):** for doing design work on the BUD.
* **On-time design (+0.25 / +0.5):** when the design phase landed within
  its estimate — the larger amount for high-complexity BUDs.

Best-effort, role-gated, deduped on ``source_ref``.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.feature_learning import FeatureLearningRepository
from app.services.phase_timing import phase_drift_on_time
from app.services.sp_rules import (
    SP_DESIGNER_CONTRIBUTION,
    SP_DESIGNER_HIGH_COMPLEXITY_MIN,
    SP_DESIGNER_ON_TIME_HIGH,
    SP_DESIGNER_ON_TIME_LOW,
)
from app.services.sp_service import award_sp, get_user_role

logger = structlog.get_logger(__name__)


async def _designers_for_bud(
    db: AsyncSession, org_id: uuid.UUID, bud: BUDDocument
) -> list[uuid.UUID]:
    """Distinct ``design_updated`` actors who hold the designer role."""
    actors = await BUDTimelineRepository(db, org_id=org_id).distinct_actors_for_event(
        bud.id, "design_updated"
    )
    return [a for a in actors if await get_user_role(db, a, org_id) == "designer"]


async def award_designer_sp_on_close(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Award design-contribution + on-time SP to the BUD's designers.

    Fully guarded so a transient failure in the setup reads (timeline / role /
    metrics) degrades to "no award" rather than breaking the close handler.
    """
    try:
        designers = await _designers_for_bud(db, org_id, bud)
        if not designers:
            return

        learning = await FeatureLearningRepository(db, org_id=org_id).get_for_bud(bud.id)
        on_time = phase_drift_on_time(learning, "design")
        high = (bud.complexity or 0) >= SP_DESIGNER_HIGH_COMPLEXITY_MIN
        on_time_amount = SP_DESIGNER_ON_TIME_HIGH if high else SP_DESIGNER_ON_TIME_LOW

        for designer_id in designers:
            await award_sp(
                db,
                user_id=designer_id,
                org_id=org_id,
                amount=SP_DESIGNER_CONTRIBUTION,
                source="sp_designer_contribution",
                source_ref=f"sp_designer:{bud.bud_number}:{designer_id}",
            )
            if on_time:
                await award_sp(
                    db,
                    user_id=designer_id,
                    org_id=org_id,
                    amount=on_time_amount,
                    source="sp_designer_on_time",
                    source_ref=f"sp_designer_ontime:{bud.bud_number}:{designer_id}",
                )
    except Exception:
        logger.warning("sp_designer_failed", bud_number=bud.bud_number, exc_info=True)
