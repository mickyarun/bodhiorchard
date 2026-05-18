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

"""Skill loader for Bodhiorchard agent skills.

Reads skill definition markdown files from backend/app/agents/skills/,
parses YAML frontmatter, and returns structured Skill objects.

Also provides DB-aware loading: per-org overrides take precedence over
file-based defaults via ``load_skill_for_org()``.
"""

import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

SKILLS_DIR = Path(__file__).parent.parent / "agents" / "skills"


@dataclass(frozen=True)
class Skill:
    """A loaded agent skill definition (immutable after construction)."""

    name: str
    slug: str
    description: str
    tools: list[str]
    mcp_tools: list[str]
    prompt: str  # Full markdown body (after frontmatter)
    max_turns: int = 0  # 0 = unlimited (omit --max-turns flag)
    timeout_seconds: int = 0  # 0 = caller's hard-coded fallback (see Skill.timeout_or_default)
    model: str = ""  # empty = use CLI default. Values: "opus", "sonnet", full model ID
    # Optional override for chat-iteration paths (e.g. BUD design chat
    # follow-ups). When empty, falls back to ``model``. Use this to put a
    # faster model on the hot iteration loop (Haiku) while keeping a
    # higher-quality model (Sonnet) for the initial agent run.
    iteration_model: str = ""
    effort: str = ""  # empty = use CLI default. Values: "low", "medium", "high", "max"

    def timeout_or_default(self, fallback: int) -> int:
        """Resolve the runtime timeout for this skill.

        Returns the per-skill DB override when set (>0), otherwise the
        caller's hard-coded fallback. Centralised so each agent's
        ``_build_config`` reads the same value the settings UI writes.
        """
        return self.timeout_seconds if self.timeout_seconds > 0 else fallback


def load_skill(skill_name: str) -> Skill:
    """Load a skill from its markdown file.

    Args:
        skill_name: The skill filename without extension (e.g., 'product-manager').

    Returns:
        A Skill object with parsed frontmatter and body.

    Raises:
        FileNotFoundError: If the skill file doesn't exist.
        ValueError: If the file has invalid frontmatter.
    """
    skill_path = SKILLS_DIR / f"{skill_name}.md"
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill not found: {skill_path}")

    content = skill_path.read_text()
    frontmatter, body = _parse_frontmatter(content)

    return Skill(
        name=frontmatter.get("name", skill_name),
        slug=skill_name,
        description=frontmatter.get("description", ""),
        tools=_parse_list(frontmatter.get("tools", "")),
        mcp_tools=_parse_list(frontmatter.get("mcp_tools", "")),
        prompt=body.strip(),
        max_turns=int(frontmatter.get("max_turns", 0)),
        timeout_seconds=int(frontmatter.get("timeout_seconds", 0)),
        model=str(frontmatter.get("model", "") or ""),
        iteration_model=str(frontmatter.get("iteration_model", "") or ""),
        effort=str(frontmatter.get("effort", "") or ""),
    )


def list_available_skills() -> list[str]:
    """List all available skill names (filenames without .md extension).

    Returns:
        Sorted list of skill names.
    """
    if not SKILLS_DIR.exists():
        return []
    return sorted(p.stem for p in SKILLS_DIR.glob("*.md"))


async def load_skill_for_org(skill_name: str, org_id: uuid.UUID, db: AsyncSession) -> Skill:
    """Load a skill from the DB for a given org.

    Skills are seeded on startup so they should always exist in the DB.

    Args:
        skill_name: The skill slug (e.g., 'product-manager').
        org_id: Organization UUID to look up the skill for.
        db: Async database session.

    Returns:
        A Skill object from the DB.

    Raises:
        ValueError: If the skill is not found in the DB.
    """
    from app.repositories.agent_skill import AgentSkillRepository

    repo = AgentSkillRepository(db, org_id=org_id)
    skill_row = await repo.get_by_slug(skill_name)

    if not skill_row:
        raise ValueError(f"Skill not found in DB: {skill_name} (org_id={org_id})")

    return Skill(
        name=skill_row.name,
        slug=skill_row.skill_slug,
        description=skill_row.description,
        tools=skill_row.tools,
        mcp_tools=skill_row.mcp_tools,
        prompt=skill_row.prompt,
        max_turns=skill_row.max_turns or 0,
        timeout_seconds=skill_row.timeout_seconds or 0,
        model=skill_row.model or "",
        iteration_model=skill_row.iteration_model or "",
        effort=skill_row.effort or "",
    )


async def seed_skills_for_org(org_id: uuid.UUID, db: AsyncSession) -> int:
    """Seed file-based skill defaults into DB for an org.

    Iterates ``AGENT_SKILL_MAP`` so each agent type gets its own row,
    even when several types share a slug (e.g. ``product-manager`` →
    bud/standup/reassignment). Re-runs are idempotent: missing rows
    are inserted with ``is_default=True``, existing rows have empty
    timeout-seconds backfilled but never clobber tuned values.

    Args:
        org_id: Organization UUID to seed for.
        db: Async database session.

    Returns:
        Number of (agent_type, slug) rows newly inserted.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from app.agents.skill_mapping import AGENT_SKILL_MAP
    from app.models.agent_skill import AgentType
    from app.repositories.agent_skill import AgentSkillRepository

    repo = AgentSkillRepository(db, org_id=org_id)

    existing_skills = await repo.list_all()
    existing_by_key: dict[tuple[str, AgentType], Any] = {
        (s.skill_slug, s.agent_type): s for s in existing_skills
    }

    seeded = 0
    backfilled = 0
    for agent_name, slug in AGENT_SKILL_MAP.items():
        try:
            agent_type = AgentType(agent_name)
        except ValueError:
            logger.warning("seed_skill_unknown_agent_type", agent=agent_name)
            continue
        try:
            skill = load_skill(slug)
        except (FileNotFoundError, ValueError, OSError):
            logger.warning("seed_skill_load_failed", skill=slug, exc_info=True)
            continue

        existing = existing_by_key.get((slug, agent_type))
        if existing is not None:
            if existing.timeout_seconds == 0 and skill.timeout_seconds > 0:
                existing.timeout_seconds = skill.timeout_seconds
                backfilled += 1
            continue

        try:
            await repo.upsert(
                skill_slug=slug,
                name=skill.name,
                description=skill.description,
                tools=skill.tools,
                mcp_tools=skill.mcp_tools,
                prompt=skill.prompt,
                max_turns=skill.max_turns,
                timeout_seconds=skill.timeout_seconds,
                model=skill.model,
                iteration_model=skill.iteration_model,
                effort=skill.effort,
                agent_type=agent_type,
                is_default=True,
            )
            seeded += 1
        except SQLAlchemyError:
            logger.warning(
                "seed_skill_db_failed", skill=slug, agent_type=agent_name, exc_info=True
            )
            continue

    if backfilled:
        await db.flush()
        logger.info("skill_timeouts_backfilled", org_id=str(org_id), count=backfilled)
    logger.info("skills_seeded", org_id=str(org_id), count=seeded)
    return seeded


def _parse_frontmatter(content: str) -> tuple[dict[str, Any], str]:
    """Parse YAML frontmatter from markdown content.

    Args:
        content: Raw markdown file content.

    Returns:
        Tuple of (frontmatter dict, body text).

    Raises:
        ValueError: If frontmatter delimiters are missing or YAML is invalid.
    """
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        raise ValueError("Invalid frontmatter: missing --- delimiters")

    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML frontmatter: {e}") from e

    return frontmatter, match.group(2)


def _parse_list(value: str | list[Any]) -> list[str]:
    """Parse a comma-separated string or list into a list of stripped strings.

    Args:
        value: Either a comma-separated string or already a list.

    Returns:
        List of stripped, non-empty strings.
    """
    if isinstance(value, list):
        return [s.strip() for s in value if s.strip()]
    return [s.strip() for s in str(value).split(",") if s.strip()]
