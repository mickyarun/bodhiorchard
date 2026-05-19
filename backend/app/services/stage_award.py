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

"""Award stage-promotion XP to a BUD's contributors.

Called from the release-detection paths (fast + SHA-walk) right after
a ``merged_to_{stage}`` timeline event is recorded. The stage's XP pool
(``STAGE_XP`` in ``xp_rules``) is split equally among every user who
contributed to the BUD — commit authors via ``DevActivityLog`` and PR
authors via ``PullRequest``, unioned by ``contributor_resolver``.

Dedup happens via ``source_ref = xp_stage:{stage}:{bud_id}:{user_id}``,
so the same (user, BUD, stage) triple is only ever credited once — even
on GitHub webhook re-delivery.

Failures are logged and swallowed: an XP-award bug must not stop the
release-event recording or break the parent webhook handler.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.contributor_resolver import get_bud_contributors
from app.services.stage_types import ReleaseStage
from app.services.xp_rules import STAGE_XP
from app.services.xp_service import award_xp

logger = structlog.get_logger(__name__)


async def award_stage_xp_to_contributors(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    stage: ReleaseStage,
) -> int:
    """Split ``STAGE_XP[stage]`` across the BUD's contributors.

    Returns the count of users newly awarded (post-dedup). Returns 0 if
    no contributors were found or the stage isn't in the rule table.
    """
    pool = STAGE_XP.get(stage)
    if pool is None:
        return 0

    contributors = await get_bud_contributors(db, org_id, bud_id)
    if not contributors:
        logger.info("stage_xp_no_contributors", bud_id=str(bud_id), stage=stage)
        return 0

    per_user = round(pool / len(contributors), 2)
    if per_user <= 0:
        return 0

    awarded = 0
    for user_id in contributors:
        try:
            result = await award_xp(
                db,
                user_id=user_id,
                org_id=org_id,
                amount=per_user,
                source=f"xp_stage_{stage}",
                source_ref=f"xp_stage:{stage}:{bud_id}:{user_id}",
                bud_id=bud_id,
            )
            if result is not None:
                awarded += 1
        except Exception:
            logger.warning(
                "stage_xp_award_failed",
                user_id=str(user_id),
                bud_id=str(bud_id),
                stage=stage,
                exc_info=True,
            )

    if awarded:
        logger.info(
            "stage_xp_awarded",
            bud_id=str(bud_id),
            stage=stage,
            contributors=len(contributors),
            per_user=per_user,
            new_awards=awarded,
        )
    return awarded
