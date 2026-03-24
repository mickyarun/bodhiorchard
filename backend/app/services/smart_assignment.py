"""Smart developer assignment based on skill profiles and workload.

Scores developers by skill match (50%), workload (30%), and recency (20%)
to intelligently assign the DEVELOPMENT phase of a BUD.
"""

import json
import re
import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.skill_profile import SkillProfile
from app.models.user import User, UserRole
from app.services.bud_assignment import _TERMINAL_STATUSES

logger = structlog.get_logger(__name__)

# Max active BUDs before a developer is excluded from candidates
_MAX_ACTIVE_BUDS = 3

# Scoring weights
_W_SKILL = 0.5
_W_WORKLOAD = 0.3
_W_RECENCY = 0.2


def _extract_modules_regex(tech_spec_md: str) -> set[str]:
    """Fast regex fallback for module extraction.

    Extracts first-level directory names from file paths mentioned in the
    tech spec text.  Used when the LLM extractor fails or times out.
    """
    modules: set[str] = set()

    for match in re.finditer(r"(?:[\w.-]+/){1,6}[\w.-]+", tech_spec_md):
        first_dir = match.group().split("/")[0].lower()
        if first_dir and len(first_dir) > 2:
            modules.add(first_dir)

    for match in re.finditer(r"(\w+)\s+(?:module|service|component|package)", tech_spec_md, re.I):
        modules.add(match.group(1).lower())

    return modules


async def _extract_modules_llm(
    tech_spec_md: str,
    known_modules: set[str],
) -> set[str]:
    """Use a lightweight LLM call to extract relevant modules from a tech spec.

    The LLM is told which module names exist in the codebase (from
    SkillProfile records) and asked to pick the ones this tech plan touches.
    Falls back to regex extraction on any failure.
    """
    try:
        from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

        known_list = ", ".join(sorted(known_modules)) if known_modules else "(none)"
        snippet = tech_spec_md[:3000]

        prompt = (
            "Extract the top-level repository modules (directory names) that "
            "this tech plan will touch. Reply with ONLY a JSON array of "
            "lowercase strings. No explanation.\n\n"
            f"Known modules in this codebase: {known_list}\n\n"
            f"Tech plan:\n{snippet}\n\n"
            'Example output: ["backend", "frontend", "docs"]'
        )

        config = ClaudeRunnerConfig(max_turns=1, timeout_seconds=60)
        result = await run_claude_code(prompt=prompt, config=config)

        if result.success and result.output:
            # Parse JSON array from output (tolerant of markdown fences)
            text = result.output.strip()
            # Strip markdown code fences if present
            if text.startswith("```"):
                text = re.sub(r"^```\w*\n?", "", text)
                text = re.sub(r"\n?```$", "", text)
            parsed = json.loads(text.strip())
            if isinstance(parsed, list):
                return {str(m).lower() for m in parsed if isinstance(m, str)}
    except Exception:
        logger.warning("llm_module_extraction_failed")

    return _extract_modules_regex(tech_spec_md)


async def _extract_modules(
    tech_spec_md: str | None,
    known_modules: set[str] | None = None,
) -> set[str]:
    """Extract modules from a tech spec using LLM with regex fallback.

    If known_modules are provided (from SkillProfile data), the LLM can
    target the exact vocabulary.  Otherwise falls back to regex only.
    """
    if not tech_spec_md:
        return set()

    if known_modules:
        return await _extract_modules_llm(tech_spec_md, known_modules)

    return _extract_modules_regex(tech_spec_md)


async def score_developers(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    exclude_user_ids: list[uuid.UUID] | None = None,
) -> list[tuple[User, float]]:
    """Score all eligible developers in the org for a BUD.

    Returns sorted list of (User, score) descending by score.
    Excludes developers with >= 3 active BUDs.
    """
    exclude_ids = set(exclude_user_ids or [])

    # Find active developers
    result = await db.execute(
        select(User).where(
            User.org_id == org_id,
            User.role == UserRole.DEVELOPER,
            User.is_active == true(),
        )
    )
    candidates = [u for u in result.scalars().all() if u.id not in exclude_ids]
    if not candidates:
        return []

    candidate_ids = [c.id for c in candidates]

    # Count active BUDs per candidate
    load_result = await db.execute(
        select(BUDDocument.assignee_id, func.count())
        .where(
            BUDDocument.org_id == org_id,
            BUDDocument.assignee_id.in_(candidate_ids),
            BUDDocument.status.notin_([s.value for s in _TERMINAL_STATUSES]),
        )
        .group_by(BUDDocument.assignee_id)
    )
    load_map: dict[uuid.UUID, int] = {row[0]: row[1] for row in load_result}

    # Filter out overloaded developers
    candidates = [c for c in candidates if load_map.get(c.id, 0) < _MAX_ACTIVE_BUDS]
    if not candidates:
        return []

    max_load = max(load_map.get(c.id, 0) for c in candidates) or 1

    # Fetch skill profiles for candidates (needed for both module extraction and scoring)
    skill_result = await db.execute(
        select(SkillProfile).where(
            SkillProfile.org_id == org_id,
            SkillProfile.user_id.in_([c.id for c in candidates]),
        )
    )
    all_skills = list(skill_result.scalars().all())

    # Gather known module names so the LLM can target the right vocabulary
    known_modules = {sp.module.lower() for sp in all_skills}

    # Extract modules from tech spec (LLM-powered with regex fallback)
    modules = await _extract_modules(bud.tech_spec_md, known_modules)

    # Group skills by user
    user_skills: dict[uuid.UUID, list[SkillProfile]] = {}
    for sp in all_skills:
        user_skills.setdefault(sp.user_id, []).append(sp)

    now = datetime.now(UTC)
    scored: list[tuple[User, float]] = []

    for candidate in candidates:
        skills = user_skills.get(candidate.id, [])

        # Skill match score (0-1): weighted by overlap with tech spec modules
        skill_score = 0.0
        if modules and skills:
            matching = [sp for sp in skills if sp.module.lower() in modules]
            if matching:
                raw = sum(float(sp.skill_score) * sp.touch_count for sp in matching)
                max_possible = max(
                    sum(float(sp.skill_score) * sp.touch_count for sp in skills), 1.0
                )
                skill_score = min(raw / max_possible, 1.0)

        # Workload score (0-1): fewer active BUDs = higher score
        active_count = load_map.get(candidate.id, 0)
        workload_score = 1.0 - (active_count / max_load)

        # Recency score (0-1): more recent touches = higher score
        recency_score = 0.0
        if skills:
            recent_touches = [
                sp.last_touch
                for sp in skills
                if sp.last_touch is not None
                and (sp.module.lower() in modules if modules else True)
            ]
            if recent_touches:
                most_recent = max(recent_touches)
                days_ago = (now - most_recent).days
                # Normalize: 0 days = 1.0, 365+ days = 0.0
                recency_score = max(0.0, 1.0 - (days_ago / 365.0))

        total = _W_SKILL * skill_score + _W_WORKLOAD * workload_score + _W_RECENCY * recency_score
        scored.append((candidate, total))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def assign_best_developer(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    exclude_user_ids: list[uuid.UUID] | None = None,
) -> User | None:
    """Pick the best developer for a BUD based on skill profiles.

    Returns the top-scoring developer, or None if no candidates exist.
    When the top 2 candidates are within 10% of each other, uses an LLM
    tiebreak for the final decision.
    """
    scored = await score_developers(db, org_id, bud, exclude_user_ids)
    if not scored:
        return None

    if len(scored) == 1:
        return scored[0][0]

    top_user, top_score = scored[0]
    runner_up_user, runner_up_score = scored[1]

    # If scores are within 10%, use LLM tiebreak
    if top_score > 0 and (top_score - runner_up_score) / top_score < 0.10:
        winner = await _llm_tiebreak(bud, top_user, runner_up_user)
        if winner:
            return winner

    return top_user


async def _llm_tiebreak(
    bud: BUDDocument,
    candidate_a: User,
    candidate_b: User,
) -> User | None:
    """Use a lightweight LLM call to break a tie between two candidates."""
    try:
        from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code

        prompt = (
            f"You must pick one developer for this task. Reply with ONLY the name.\n\n"
            f"Task: {bud.title}\n"
            f"Tech plan summary: {(bud.tech_spec_md or '')[:500]}\n\n"
            f"Candidate A: {candidate_a.name} ({candidate_a.email})\n"
            f"Candidate B: {candidate_b.name} ({candidate_b.email})\n\n"
            f"Who is the better fit? Reply with exactly one name."
        )

        config = ClaudeRunnerConfig(max_turns=1, timeout_seconds=60)
        result = await run_claude_code(prompt=prompt, config=config)

        if result.success and result.output:
            output = result.output.strip().lower()
            if candidate_a.name.lower() in output:
                return candidate_a
            if candidate_b.name.lower() in output:
                return candidate_b
    except Exception:
        logger.warning("llm_tiebreak_failed", bud_id=str(bud.id))

    return None


async def reassign_developer(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    current_assignee_id: uuid.UUID,
    reason: str,
) -> User | None:
    """Reassign a BUD to the next-best developer, excluding the current one.

    No LLM fallback for reassignment — just picks the top scorer.
    """
    scored = await score_developers(db, org_id, bud, exclude_user_ids=[current_assignee_id])
    if not scored:
        logger.info(
            "reassign_no_candidates",
            bud_id=str(bud.id),
            reason=reason,
        )
        return None

    return scored[0][0]
