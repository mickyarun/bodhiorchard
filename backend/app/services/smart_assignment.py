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

"""Smart role-based assignment using skill profiles and workload.

Scores candidates by skill match (50%), workload (30%), and recency
(20%) to pick the best person for a BUD phase. When the inputs the
formula needs aren't available (no ``impacted_repos`` on the BUD, or
no skill_profile rows for the role — true for PMs / Designers / Tech
Leads / QAs who don't have git activity), the scorer short-circuits to
**workload-only ranking**: still deterministic, but no fake skill score
and no wasted LLM tiebreak between effectively-identical candidates.

The caller (``bud_assignment.auto_assign_for_phase``) is responsible
for filtering candidates to those under their role's capacity limit
and for fetching the active-BUD ``load_map`` once — both are passed in
here to avoid a duplicate query.
"""

import uuid
from datetime import UTC, datetime

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.models.skill_profile import SkillProfile
from app.models.user import User, UserRole
from app.repositories.skill_profile import SkillProfileRepository

logger = structlog.get_logger(__name__)

# Scoring weights — must sum to 1.0.
_W_SKILL = 0.5
_W_WORKLOAD = 0.3
_W_RECENCY = 0.2

# An LLM tiebreak only adds value when there's a real signal to break a
# tie on. Workload-only scores cap at ``_W_WORKLOAD`` (0.3), so a top
# score at or below that threshold means skill + recency contributed
# zero — calling Claude to pick between two zeros is wasted work.
_MIN_SCORE_FOR_LLM_TIEBREAK = _W_WORKLOAD


async def score_candidates(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    candidates: list[User],
    load_map: dict[uuid.UUID, int],
) -> list[tuple[User, float]]:
    """Score each candidate for this BUD; return descending by score.

    Caller has already filtered ``candidates`` to those eligible (under
    their role's capacity cap) and pre-fetched ``load_map`` (active-BUD
    count per candidate). We do the scoring math here only.

    Layer 1 short-circuit: if the BUD has no ``impacted_repos`` or none
    of the candidates have any ``skill_profile`` rows, drop the skill +
    recency components and rank by workload only. Returned scores cap at
    ``_W_WORKLOAD`` (0.3) in that mode — the caller uses that as a
    signal to skip the LLM tiebreak (see ``assign_best_for_role``).
    """
    if not candidates:
        return []

    max_load = max(load_map.get(c.id, 0) for c in candidates) or 1

    all_skills = await SkillProfileRepository(db, org_id=org_id).list_for_users(
        [c.id for c in candidates]
    )
    modules = {
        r.get("repo_name", "").lower() for r in (bud.impacted_repos or []) if r.get("repo_name")
    }

    scored: list[tuple[User, float]] = []

    if not modules or not all_skills:
        # No skill/recency signal available — rank by workload alone.
        for c in candidates:
            scored.append((c, _W_WORKLOAD * (1.0 - load_map.get(c.id, 0) / max_load)))
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored

    user_skills: dict[uuid.UUID, list[SkillProfile]] = {}
    for sp in all_skills:
        user_skills.setdefault(sp.user_id, []).append(sp)

    now = datetime.now(UTC)

    for candidate in candidates:
        skills = user_skills.get(candidate.id, [])

        skill_score = 0.0
        if skills:
            matching = [sp for sp in skills if sp.module.lower() in modules]
            if matching:
                raw = sum(float(sp.skill_score) * sp.touch_count for sp in matching)
                max_possible = max(
                    sum(float(sp.skill_score) * sp.touch_count for sp in skills), 1.0
                )
                skill_score = min(raw / max_possible, 1.0)

        workload_score = 1.0 - (load_map.get(candidate.id, 0) / max_load)

        recency_score = 0.0
        if skills:
            recent_touches = [
                sp.last_touch
                for sp in skills
                if sp.last_touch is not None and sp.module.lower() in modules
            ]
            if recent_touches:
                days_ago = (now - max(recent_touches)).days
                recency_score = max(0.0, 1.0 - (days_ago / 365.0))

        total = _W_SKILL * skill_score + _W_WORKLOAD * workload_score + _W_RECENCY * recency_score
        scored.append((candidate, total))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored


async def assign_best_for_role(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    role: UserRole,
    candidates: list[User],
    load_map: dict[uuid.UUID, int],
) -> User | None:
    """Pick the best candidate. LLM tiebreak only on meaningful scores.

    - No candidates → ``None`` (caller falls through to round-robin).
    - One candidate → that one.
    - Top score at/below ``_MIN_SCORE_FOR_LLM_TIEBREAK`` → top one
      (workload-only mode; nothing for the LLM to differentiate).
    - Otherwise, if top 2 are within 10% → LLM tiebreak.
    """
    scored = await score_candidates(db, org_id, bud, candidates, load_map)
    if not scored:
        return None
    if len(scored) == 1:
        return scored[0][0]

    top_user, top_score = scored[0]
    if top_score <= _MIN_SCORE_FOR_LLM_TIEBREAK:
        return top_user

    runner_up_user, runner_up_score = scored[1]
    if top_score > 0 and (top_score - runner_up_score) / top_score < 0.10:
        winner = await _llm_tiebreak(bud, top_user, runner_up_user)
        if winner:
            return winner

    return top_user


async def reassign_developer(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud: BUDDocument,
    current_assignee_id: uuid.UUID,
    reason: str,
) -> User | None:
    """Reassign a BUD to the next-best developer, excluding the current one.

    No LLM fallback. Independently fetches the developer pool +
    ``load_map`` (this path isn't part of the chain walk) and applies
    the developer-role capacity cap.
    """
    from app.repositories.bud import BUDRepository
    from app.repositories.user import UserRepository
    from app.services.bud_assignment import _TERMINAL_STATUSES, max_active_buds_for

    user_repo = UserRepository(db)
    bud_repo = BUDRepository(db, org_id=org_id)
    all_devs = await user_repo.list_active_with_role(org_id, UserRole.DEVELOPER)
    eligible = [u for u in all_devs if u.id != current_assignee_id]
    if not eligible:
        logger.info("reassign_no_candidates", bud_id=str(bud.id), reason=reason)
        return None

    load_map = await bud_repo.count_active_loads_for_assignees(
        [c.id for c in eligible], [s.value for s in _TERMINAL_STATUSES]
    )
    cap = max_active_buds_for(UserRole.DEVELOPER)
    under_cap = [c for c in eligible if load_map.get(c.id, 0) < cap]
    if not under_cap:
        logger.info("reassign_all_at_capacity", bud_id=str(bud.id), reason=reason)
        return None

    scored = await score_candidates(db, org_id, bud, under_cap, load_map)
    return scored[0][0] if scored else None


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
