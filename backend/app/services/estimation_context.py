"""Context gathering for BUD estimation.

Collects backlog depth, assignee workload, developer skill profiles,
and historical calibration data to feed the estimation engine.
"""

import uuid

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument, BUDStatus
from app.models.skill_profile import SkillProfile

logger = structlog.get_logger(__name__)

_TERMINAL_STATUSES = {BUDStatus.CLOSED, BUDStatus.DISCARDED, BUDStatus.PROD}

# Phases where developer SkillProfile data improves estimates.
SKILL_AWARE_PHASES = {"development", "code_review", "testing"}


def compute_bud_complexity(bud: BUDDocument) -> int:
    """Derive complexity score from BUD content signals."""
    from app.services.estimation_engine import compute_complexity

    qa_count = len(bud.qa_automation_cases or []) + len(bud.qa_manual_cases or [])
    return compute_complexity(
        requirements_len=len(bud.requirements_md or ""),
        tech_spec_len=len(bud.tech_spec_md or ""),
        impacted_repo_count=len(bud.impacted_repos or []),
        qa_case_count=qa_count,
    )


async def get_backlog_context(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> dict:
    """Gather backlog depth and assignee workload."""
    from app.repositories.bud_estimate import BUDEstimateQueryRepository

    est_repo = BUDEstimateQueryRepository(db, org_id=org_id)
    status_val = bud.status.value if isinstance(bud.status, BUDStatus) else bud.status
    queue_depth = await est_repo.count_ahead_in_queue(bud.bud_number, status_val)

    assignee_workload = 0
    if bud.assignee_id:
        result = await db.execute(
            select(func.count())
            .select_from(BUDDocument)
            .where(
                BUDDocument.org_id == org_id,
                BUDDocument.assignee_id == bud.assignee_id,
                BUDDocument.status.notin_([s.value for s in _TERMINAL_STATUSES]),
                BUDDocument.id != bud.id,
            )
        )
        assignee_workload = result.scalar_one()

    return {"queue_depth": queue_depth, "assignee_workload": assignee_workload}


async def get_skill_context(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
) -> dict | None:
    """Get assignee's skill profile data for skill-aware phases."""
    current_status = bud.status.value if isinstance(bud.status, BUDStatus) else bud.status
    if current_status not in SKILL_AWARE_PHASES or not bud.assignee_id:
        return None

    # Get assignee's skill profiles directly — no LLM call needed.
    # The estimation LLM reads the tech spec and judges relevance itself.
    sp_result = await db.execute(
        select(SkillProfile).where(
            SkillProfile.org_id == org_id,
            SkillProfile.user_id == bud.assignee_id,
        )
    )
    assignee_skills = list(sp_result.scalars().all())
    modules = {sp.module.lower() for sp in assignee_skills}

    return {
        "modules_known": list(modules),
        "module_count": len(assignee_skills),
        "avg_skill_score": (
            sum(float(sp.skill_score) for sp in assignee_skills) / len(assignee_skills)
            if assignee_skills
            else 0.0
        ),
        "skill_details": [
            {
                "module": sp.module,
                "score": float(sp.skill_score),
                "touches": sp.touch_count,
                "languages": sp.languages or [],
            }
            for sp in assignee_skills
        ],
    }


async def get_historical_context(
    db: AsyncSession,
    org_id: uuid.UUID,
) -> str:
    """Build few-shot historical context from completed BUDs (if any)."""
    result = await db.execute(
        select(BUDDocument)
        .where(
            BUDDocument.org_id == org_id,
            BUDDocument.status.in_([BUDStatus.PROD.value, BUDStatus.CLOSED.value]),
            BUDDocument.estimated_dates.isnot(None),
        )
        .order_by(BUDDocument.updated_at.desc())
        .limit(5)
    )
    completed = list(result.scalars().all())
    if not completed:
        return ""

    lines = ["Historical data from completed features in this org:"]
    for b in completed:
        complexity = b.complexity or "?"
        cycle = max(1, (b.updated_at - b.created_at).days) if b.created_at else 0
        lines.append(f"- Feature (complexity {complexity}): completed in ~{cycle} days")
    return "\n".join(lines)
