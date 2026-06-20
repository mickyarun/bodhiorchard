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

"""Orchestrate every developer Skill-Point award at BUD close.

Gathers the BUD's completed todos and reviewers, runs the substance/review
judge exactly once (it self-skips when there's nothing to weigh), then
applies each developer rule with the shared verdict:

* BUD-shipped pool, split across the people who did the work.
* Code-review SP per valid, non-self reviewer.
* Quality bonus or over-threshold bug penalty for the developers.

Every rule is best-effort: a failure in one is logged and swallowed so it
never blocks the others or the parent close handler. All awards dedup on
``source_ref`` so re-close / backfill replays are safe.
"""

from __future__ import annotations

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.bud_todo import BUDTodoStatus
from app.models.organization import Organization
from app.repositories.bud_todo import BUDTodoRepository
from app.services.bud_shipped_sp import resolve_shipped_weights
from app.services.code_review_sp import award_code_review_sp
from app.services.contributor_resolver import get_bud_contributors
from app.services.dev_quality_sp import award_quality_and_threshold_sp
from app.services.sp_attribution import TodoForJudgment, judge_sp_attribution
from app.services.sp_rules import SP_DEV_BUD_SHIPPED
from app.services.sp_split import award_split_sp

logger = structlog.get_logger(__name__)


async def _gather_judgment_inputs(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> tuple[list[TodoForJudgment], list[str]]:
    """Completed todos (for substance) + reviewer logins (for validity)."""
    todo_repo = BUDTodoRepository(db, org_id=org_id)
    todos = [
        TodoForJudgment(
            todo_id=str(t.id),
            assignee_id=t.assignee_id,
            title=t.title or "",
            description=t.description or "",
        )
        for t in await todo_repo.list_for_bud(bud.id)
        if t.status == BUDTodoStatus.COMPLETED.value
        and not t.is_checkpoint
        and t.assignee_id is not None
    ]
    reviewers = sorted(
        {
            entry["author"]
            for entry in (bud.code_review_comments or [])
            if isinstance(entry, dict)
            and entry.get("author")
            and (entry.get("body") or "").strip()
        }
    )
    return todos, reviewers


async def award_developer_sp_on_close(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> None:
    """Run all developer SP rules for a BUD that reached prod / closed."""
    # Setup (gather + judge + weight resolution) is guarded as a unit: the
    # judge never raises, but the surrounding DB reads can, and a setup
    # failure must degrade to "no SP awarded" rather than break the parent
    # close handler.
    try:
        todos, reviewers = await _gather_judgment_inputs(db, org_id, bud)
        attribution = await judge_sp_attribution(todos, reviewers)
        weights = await resolve_shipped_weights(db, org_id, bud, attribution.todo_weights)
    except Exception:
        logger.warning("sp_developer_setup_failed", bud_number=bud.bud_number, exc_info=True)
        return

    # Only positively-weighted developers count as recipients — someone whose
    # todos were all judged trivial (weight ~0) earns no shipped split and is
    # not eligible for the quality bonus / threshold penalty either.
    dev_recipients = {uid for uid, weight in weights.items() if weight > 0}

    try:
        await award_split_sp(
            db,
            org_id,
            pool=SP_DEV_BUD_SHIPPED,
            weights=weights,
            source="sp_bud_shipped",
            ref_prefix="sp_bud_shipped",
            bud_number=bud.bud_number,
        )
    except Exception:
        logger.warning("sp_bud_shipped_failed", bud_number=bud.bud_number, exc_info=True)

    try:
        # Self-review earns nothing: exclude anyone who did work on the BUD
        # (todo recipients + commit/PR contributors).
        contributors = await get_bud_contributors(db, org_id, bud.id)
        await award_code_review_sp(
            db,
            org_id,
            bud,
            attribution.review_validity,
            exclude_user_ids=dev_recipients | contributors,
        )
    except Exception:
        logger.warning("sp_code_review_failed", bud_number=bud.bud_number, exc_info=True)

    try:
        org = await db.get(Organization, org_id)
        await award_quality_and_threshold_sp(
            db,
            org_id,
            bud,
            dev_recipients,
            org_config=org.config if org else None,
        )
    except Exception:
        logger.warning("sp_quality_threshold_failed", bud_number=bud.bud_number, exc_info=True)
