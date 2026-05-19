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

"""End-to-end behaviour of the custom-skill + per-BUD-override flow.

Exercises the layer that the SettingsAgentPrompts UI and the BUD-create
"Advanced settings" dialog will rely on. Specifically asserts:

* The seed splits ``product-manager`` into one row per agent_type that
  references it (bud, standup, reassignment) and marks each ``is_default``.
* ``set_default`` on a custom skill demotes the seeded default for the
  same agent_type and the partial unique index keeps "exactly one
  default per (org, agent_type)" intact.
* ``delete_custom`` removes user-authored rows but refuses seeded ones.
* ``resolve_skill_for_agent`` returns: per-BUD override > org default >
  fallback slug — in that priority.

Gated by ``@pytest.mark.integration``; skipped by default.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agents.skill_mapping import resolve_skill_for_agent
from app.models.agent_activity import AgentActivityLog
from app.models.agent_skill import AgentSkill, AgentType
from app.models.bud import BUDDocument, BUDStatus
from app.models.bud_stage_skill_override import BUDStageSkillOverride
from app.models.organization import Organization
from app.repositories.agent_skill import AgentSkillRepository
from app.repositories.bud_stage_skill_override import (
    BUDStageSkillOverrideRepository,
)
from app.services.skill_loader import resolve_skill_for_org, seed_skills_for_org

pytestmark = pytest.mark.integration


async def _seed_org(factory: async_sessionmaker[AsyncSession]) -> uuid.UUID:
    async with factory() as db:
        org = Organization(
            name=f"Skills Test Org {uuid.uuid4()}",
            slug=f"skills-{uuid.uuid4().hex[:8]}",
        )
        db.add(org)
        await db.flush()
        await db.commit()
        return org.id


async def _seed_bud(factory: async_sessionmaker[AsyncSession], org_id: uuid.UUID) -> uuid.UUID:
    async with factory() as db:
        bud = BUDDocument(
            org_id=org_id,
            bud_number=1,
            title="Override Test BUD",
            status=BUDStatus.BUD,
        )
        db.add(bud)
        await db.flush()
        await db.commit()
        return bud.id


@pytest.mark.asyncio
async def test_seed_splits_shared_slugs_per_agent_type(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``product-manager`` (3 agent types) should end up as 3 rows, all default."""
    org_id = await _seed_org(pg_session_factory)

    async with pg_session_factory() as db:
        await seed_skills_for_org(org_id, db)
        await db.commit()

    async with pg_session_factory() as db:
        rows = (
            (
                await db.execute(
                    select(AgentSkill)
                    .where(AgentSkill.org_id == org_id)
                    .where(AgentSkill.skill_slug == "product-manager")
                )
            )
            .scalars()
            .all()
        )

    agent_types = {r.agent_type for r in rows}
    assert agent_types == {AgentType.BUD, AgentType.STANDUP, AgentType.REASSIGNMENT}
    assert all(r.is_default for r in rows)
    assert not any(r.is_custom for r in rows)


@pytest.mark.asyncio
async def test_set_default_flips_prior_default_for_agent_type(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Promoting a custom skill demotes the seeded one in the same agent_type."""
    org_id = await _seed_org(pg_session_factory)

    async with pg_session_factory() as db:
        await seed_skills_for_org(org_id, db)
        await db.commit()

    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        custom = await repo.create_custom(
            skill_slug="my-pm",
            agent_type=AgentType.BUD,
            name="My PM",
            description="Tweaked PM persona",
            tools=[],
            mcp_tools=[],
            prompt="Custom prompt body",
        )
        await db.commit()
        custom_id = custom.id

    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        promoted = await repo.set_default(custom_id)
        await db.commit()
        assert promoted.is_default is True

    async with pg_session_factory() as db:
        defaults = (
            (
                await db.execute(
                    select(AgentSkill)
                    .where(AgentSkill.org_id == org_id)
                    .where(AgentSkill.agent_type == AgentType.BUD)
                    .where(AgentSkill.is_default.is_(True))
                )
            )
            .scalars()
            .all()
        )
    # Exactly one row remains default for the BUD agent type.
    assert len(defaults) == 1
    assert defaults[0].id == custom_id


@pytest.mark.asyncio
async def test_delete_custom_refuses_seeded_row(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Seeded rows must survive ``delete_custom``; only custom rows go."""
    org_id = await _seed_org(pg_session_factory)

    async with pg_session_factory() as db:
        await seed_skills_for_org(org_id, db)
        await db.commit()

    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        seeded = await repo.get_by_slug("designer", agent_type=AgentType.DESIGN)
        assert seeded is not None
        deleted = await repo.delete_custom(seeded.id)
        await db.commit()
    assert deleted is False

    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        custom = await repo.create_custom(
            skill_slug="my-designer",
            agent_type=AgentType.DESIGN,
            name="Custom Designer",
            description="",
            tools=[],
            mcp_tools=[],
            prompt="x",
        )
        await db.commit()
        custom_id = custom.id

    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        deleted = await repo.delete_custom(custom_id)
        await db.commit()
    assert deleted is True


@pytest.mark.asyncio
async def test_resolve_priority_override_then_default_then_fallback(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """resolve_skill_for_agent: per-BUD override beats org default beats fallback."""
    org_id = await _seed_org(pg_session_factory)

    async with pg_session_factory() as db:
        await seed_skills_for_org(org_id, db)
        await db.commit()

    bud_id = await _seed_bud(pg_session_factory, org_id)

    # Default resolution: org default for 'bud' agent → seeded product-manager.
    async with pg_session_factory() as db:
        default_skill = await resolve_skill_for_agent("bud", org_id, db)
        assert default_skill is not None
        assert default_skill.skill_slug == "product-manager"
        assert default_skill.agent_type == AgentType.BUD

    # Add a custom skill and pin it as the BUD's per-stage override.
    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        custom = await repo.create_custom(
            skill_slug="pm-for-this-bud",
            agent_type=AgentType.BUD,
            name="PM for this BUD",
            description="",
            tools=[],
            mcp_tools=[],
            prompt="override-only prompt",
        )
        await db.commit()
        custom_id = custom.id

    async with pg_session_factory() as db:
        override_repo = BUDStageSkillOverrideRepository(db, org_id=org_id)
        await override_repo.bulk_set_for_bud(bud_id, {BUDStatus.BUD: custom_id})
        await db.commit()

    # Per-BUD override wins.
    async with pg_session_factory() as db:
        resolved = await resolve_skill_for_agent(
            "bud", org_id, db, bud_id=bud_id, bud_status=BUDStatus.BUD
        )
        assert resolved is not None
        assert resolved.id == custom_id

    # Without the bud_id, we still get the org default (seeded PM).
    async with pg_session_factory() as db:
        resolved = await resolve_skill_for_agent("bud", org_id, db)
        assert resolved is not None
        assert resolved.skill_slug == "product-manager"


@pytest.mark.asyncio
async def test_override_cleared_when_bud_deleted(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``ON DELETE CASCADE`` on bud_id removes overrides when their BUD goes away."""
    org_id = await _seed_org(pg_session_factory)

    async with pg_session_factory() as db:
        await seed_skills_for_org(org_id, db)
        await db.commit()

    bud_id = await _seed_bud(pg_session_factory, org_id)

    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        custom = await repo.create_custom(
            skill_slug="ephemeral-pm",
            agent_type=AgentType.BUD,
            name="Ephemeral",
            description="",
            tools=[],
            mcp_tools=[],
            prompt="x",
        )
        await db.commit()
        override_repo = BUDStageSkillOverrideRepository(db, org_id=org_id)
        await override_repo.bulk_set_for_bud(bud_id, {BUDStatus.BUD: custom.id})
        await db.commit()

    async with pg_session_factory() as db:
        bud = await db.get(BUDDocument, bud_id)
        assert bud is not None
        await db.delete(bud)
        await db.commit()

    async with pg_session_factory() as db:
        count = (
            await db.execute(
                select(func.count())
                .select_from(BUDStageSkillOverride)
                .where(BUDStageSkillOverride.bud_id == bud_id)
            )
        ).scalar_one()
    assert count == 0


@pytest.mark.asyncio
async def test_resolve_skill_for_org_uses_fallback_slug_when_no_match(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """``fallback_slug`` is the last-resort shape for callers (job_design,
    job_chat) that need a Skill object even when the agent-type-aware
    chain comes up empty (e.g. on a fresh org before seed_skills_for_org
    has finished, or for legacy section slugs not in the agent map)."""
    org_id = await _seed_org(pg_session_factory)

    async with pg_session_factory() as db:
        await seed_skills_for_org(org_id, db)
        await db.commit()

    # Provoke a "no override, no default" miss by asking for an agent_type
    # whose seed is present but is_default has been demoted (simulate by
    # passing a bogus agent_name string that doesn't match any AgentType
    # — the resolver returns None, fallback_slug kicks in).
    async with pg_session_factory() as db:
        skill = await resolve_skill_for_org(
            "not-a-real-agent",
            org_id,
            db,
            fallback_slug="designer",
        )
    assert skill is not None
    assert skill.slug == "designer"


@pytest.mark.asyncio
async def test_delete_custom_skill_nulls_activity_log_skill_id(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Deleting a custom skill that has activity-log history must succeed.

    Audit rows survive with ``skill_id = NULL`` and the denormalised
    ``skill_slug`` text column intact. Without this, the NO-ACTION FK
    would permanently lock any skill that's ever been invoked.
    """
    org_id = await _seed_org(pg_session_factory)

    async with pg_session_factory() as db:
        await seed_skills_for_org(org_id, db)
        await db.commit()

    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        custom = await repo.create_custom(
            skill_slug="logged-pm",
            agent_type=AgentType.BUD,
            name="Logged PM",
            description="",
            tools=[],
            mcp_tools=[],
            prompt="x",
        )
        await db.commit()
        custom_id = custom.id

    # Insert a fake activity-log row pointing at the custom skill — the
    # row that the runtime path would normally create on each invocation.
    async with pg_session_factory() as db:
        log = AgentActivityLog(
            org_id=org_id,
            skill_id=custom_id,
            skill_slug="logged-pm",
            event_type="skill_invoked",
            source="test",
            message="test log row",
        )
        db.add(log)
        await db.commit()
        log_id = log.id

    # Delete the custom skill. Should succeed (no FK violation).
    async with pg_session_factory() as db:
        repo = AgentSkillRepository(db, org_id=org_id)
        deleted = await repo.delete_custom(custom_id)
        await db.commit()
    assert deleted is True

    # The audit row survives with skill_id nulled but skill_slug retained.
    async with pg_session_factory() as db:
        fetched = await db.get(AgentActivityLog, log_id)
        assert fetched is not None
        assert fetched.skill_id is None
        assert fetched.skill_slug == "logged-pm"


@pytest.mark.asyncio
async def test_old_bud_without_override_resolves_to_org_default(
    pg_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    """Pre-existing BUDs (no ``bud_stage_skill_overrides`` rows) must fall
    through to the org default — proves the wiring doesn't regress old
    data when the new resolver path replaces the legacy slug lookup."""
    org_id = await _seed_org(pg_session_factory)

    async with pg_session_factory() as db:
        await seed_skills_for_org(org_id, db)
        await db.commit()

    bud_id = await _seed_bud(pg_session_factory, org_id)

    # No override rows exist for this BUD — it represents the "released
    # before custom-skills landed" cohort.
    async with pg_session_factory() as db:
        resolved = await resolve_skill_for_agent(
            "design", org_id, db, bud_id=bud_id, bud_status=BUDStatus.DESIGN
        )
        assert resolved is not None
        assert resolved.skill_slug == "designer"
        assert resolved.is_default is True
