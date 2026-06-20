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

"""Tech-arch (tech-lead) on-time Skill-Point rule, settled at BUD close.

The tech lead who moved the BUD from tech-arch into development earns SP
when they did so within the tech-arch estimate. The tech lead's *code
review* SP is handled by the shared review path (``code_review_sp`` via the
developer orchestrator), and a tech lead who also wrote development todos is
already paid through the developer shipped split — so this module covers
only the tech-arch timing reward.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.repositories.bud_timeline import BUDTimelineRepository
from app.repositories.feature_learning import FeatureLearningRepository
from app.services.phase_timing import phase_drift_on_time
from app.services.sp_rules import SP_TL_TECHARCH_ON_TIME
from app.services.sp_service import award_sp, get_user_role

logger = structlog.get_logger(__name__)


async def award_tech_arch_sp_on_close(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Award the tech lead for moving the BUD to development within estimate.

    Fully guarded — the setup reads (timeline, role, metrics) are inside the
    try so a transient DB failure degrades to "no award" rather than breaking
    the parent close handler.
    """
    try:
        mover = await BUDTimelineRepository(db, org_id=org_id).first_status_change_to(
            bud.id, BUDStatus.DEVELOPMENT.value
        )
        if mover is None or mover[0] is None:
            return
        tl_id = mover[0]
        if await get_user_role(db, tl_id, org_id) != "tech_lead":
            return
        learning = await FeatureLearningRepository(db, org_id=org_id).get_for_bud(bud.id)
        if not phase_drift_on_time(learning, "tech_arch"):
            return
        await award_sp(
            db,
            user_id=tl_id,
            org_id=org_id,
            amount=SP_TL_TECHARCH_ON_TIME,
            source="sp_tl_techarch",
            source_ref=f"sp_tl_techarch:{bud.bud_number}:{tl_id}",
        )
    except Exception:
        logger.warning("sp_tl_techarch_failed", bud_number=bud.bud_number, exc_info=True)
