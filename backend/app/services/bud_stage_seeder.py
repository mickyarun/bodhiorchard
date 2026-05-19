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

"""BUD stage mapping seed data and seeder function.

Defines which agent skill runs at which BUD lifecycle stage,
and provides the seeder that populates the DB on startup.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

# ── Default stage mappings ────────────────────────────────────────
# Each entry maps a BUD status to the agent skill that runs when a
# BUD enters that status. execution_order supports future pipelines
# (multiple agents per stage, run sequentially).

DEFAULT_STAGE_MAPPINGS: list[dict[str, str | int]] = [
    {
        "bud_status": "bud",
        "skill_slug": "product-manager",
        "agent_type": "bud",
        "execution_order": 1,
        "output_section": "requirements_md",
    },
    {
        "bud_status": "tech_arch",
        "skill_slug": "tech-planner",
        "agent_type": "techPlan",
        "execution_order": 1,
        "output_section": "tech_spec_md",
    },
    {
        "bud_status": "code_review",
        "skill_slug": "code-reviewer",
        "agent_type": "skill",
        "execution_order": 1,
        "output_section": "test_plan_md",
    },
    {
        "bud_status": "testing",
        "skill_slug": "testing",
        "agent_type": "testPlan",
        "execution_order": 1,
        "output_section": "qa_execution_plan_md",
    },
]


async def seed_stage_mappings_for_org(org_id: uuid.UUID, db: AsyncSession) -> int:
    """Seed default agent-to-BUD-stage mappings for an org.

    Skips any ``(bud_status, execution_order)`` pair that already has a
    mapping row. Must be called *after* ``seed_skills_for_org`` so that
    skill rows exist for FK references.

    Args:
        org_id: Organization UUID to seed for.
        db: Async database session.

    Returns:
        Number of stage mappings seeded.
    """
    from app.models.agent_skill import AgentType
    from app.models.agent_skill_bud_stage import AgentSkillBudStage
    from app.repositories.agent_skill import AgentSkillRepository
    from app.repositories.agent_skill_bud_stage import AgentSkillBudStageRepository

    skill_repo = AgentSkillRepository(db, org_id=org_id)
    stage_repo = AgentSkillBudStageRepository(db, org_id=org_id)

    existing_stages = await stage_repo.list_all()
    existing_keys = {(s.bud_status, s.execution_order) for s in existing_stages}
    all_skills = await skill_repo.list_all()
    # Key by (slug, agent_type) — multi-mapped slugs (product-manager,
    # testing) appear once per agent_type since the migration split.
    skill_by_key = {(s.skill_slug, s.agent_type): s for s in all_skills}

    seeded = 0
    for mapping in DEFAULT_STAGE_MAPPINGS:
        bud_status = str(mapping["bud_status"])
        execution_order = int(mapping["execution_order"])

        if (bud_status, execution_order) in existing_keys:
            continue

        try:
            agent_type = AgentType(str(mapping["agent_type"]))
        except ValueError:
            logger.warning(
                "seed_stage_mapping_bad_agent_type",
                agent_type=mapping.get("agent_type"),
                org_id=str(org_id),
            )
            continue

        skill = skill_by_key.get((str(mapping["skill_slug"]), agent_type))
        if not skill:
            logger.warning(
                "seed_stage_mapping_skill_not_found",
                skill_slug=mapping["skill_slug"],
                agent_type=str(agent_type),
                org_id=str(org_id),
            )
            continue

        await stage_repo.create(
            AgentSkillBudStage(
                org_id=org_id,
                skill_id=skill.id,
                bud_status=bud_status,
                execution_order=execution_order,
                output_section=str(mapping.get("output_section", "")) or None,
                enabled=True,
            )
        )
        seeded += 1

    if seeded:
        logger.info("stage_mappings_seeded", org_id=str(org_id), count=seeded)
    return seeded
