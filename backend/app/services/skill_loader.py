"""Skill loader for Bodhigrove agent skills.

Reads skill definition markdown files from backend/app/agents/skills/,
parses YAML frontmatter, and returns structured Skill objects.

Also provides DB-aware loading: per-org overrides take precedence over
file-based defaults via ``load_skill_for_org()``.
"""

import re
import uuid
from dataclasses import dataclass
from pathlib import Path

import structlog
import yaml
from sqlalchemy.ext.asyncio import AsyncSession

logger = structlog.get_logger(__name__)

SKILLS_DIR = Path(__file__).parent.parent / "agents" / "skills"


@dataclass(frozen=True)
class Skill:
    """A loaded agent skill definition (immutable after construction)."""

    name: str
    description: str
    tools: list[str]
    mcp_tools: list[str]
    prompt: str  # Full markdown body (after frontmatter)
    max_turns: int = 0  # 0 = unlimited (omit --max-turns flag)
    model: str = ""  # empty = use CLI default. Values: "opus", "sonnet", full model ID
    effort: str = ""  # empty = use CLI default. Values: "low", "medium", "high", "max"


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
        description=frontmatter.get("description", ""),
        tools=_parse_list(frontmatter.get("tools", "")),
        mcp_tools=_parse_list(frontmatter.get("mcp_tools", "")),
        prompt=body.strip(),
        max_turns=int(frontmatter.get("max_turns", 0)),
        model=str(frontmatter.get("model", "") or ""),
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
    """Load a skill with DB override precedence, falling back to file.

    If the database query fails, logs a warning and falls back to the
    file-based default so that agent execution is not blocked by a
    transient DB issue.

    Args:
        skill_name: The skill slug (e.g., 'triage-analyst').
        org_id: Organization UUID to look up overrides for.
        db: Async database session.

    Returns:
        A Skill object — from DB if an override exists, otherwise from file.
    """
    from sqlalchemy.exc import SQLAlchemyError

    from app.repositories.agent_skill_override import AgentSkillOverrideRepository

    try:
        repo = AgentSkillOverrideRepository(db, org_id=org_id)
        override = await repo.get_by_slug(skill_name)
    except SQLAlchemyError:
        logger.warning(
            "skill_override_db_error_falling_back_to_file",
            skill=skill_name,
            org_id=str(org_id),
            exc_info=True,
        )
        return load_skill(skill_name)

    if override:
        return Skill(
            name=override.name,
            description=override.description,
            tools=override.tools,
            mcp_tools=override.mcp_tools,
            prompt=override.prompt,
            max_turns=getattr(override, "max_turns", 0) or 0,
            model=getattr(override, "model", "") or "",
            effort=getattr(override, "effort", "") or "",
        )
    return load_skill(skill_name)


async def seed_skills_for_org(org_id: uuid.UUID, db: AsyncSession) -> int:
    """Seed all file-based skill defaults into DB for an org.

    Skips any skill_slug that already has an override row. Individual
    skill failures (bad file or DB constraint violation) are logged
    and skipped without aborting the entire seed.

    Args:
        org_id: Organization UUID to seed for.
        db: Async database session.

    Returns:
        Number of skills seeded (new rows created).
    """
    from sqlalchemy.exc import SQLAlchemyError

    from app.repositories.agent_skill_override import AgentSkillOverrideRepository

    repo = AgentSkillOverrideRepository(db, org_id=org_id)

    # Single query to get existing slugs instead of N get_by_slug calls
    existing_overrides = await repo.list_all()
    existing_slugs = {o.skill_slug for o in existing_overrides}

    available = list_available_skills()
    seeded = 0
    for slug in available:
        if slug in existing_slugs:
            continue
        try:
            skill = load_skill(slug)
        except (FileNotFoundError, ValueError, OSError):
            logger.warning("seed_skill_load_failed", skill=slug, exc_info=True)
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
                model=skill.model,
                effort=skill.effort,
            )
            seeded += 1
        except SQLAlchemyError:
            logger.warning("seed_skill_db_failed", skill=slug, exc_info=True)
            continue
    logger.info("skills_seeded", org_id=str(org_id), count=seeded)
    return seeded


def _parse_frontmatter(content: str) -> tuple[dict, str]:
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


def _parse_list(value: str | list) -> list[str]:
    """Parse a comma-separated string or list into a list of stripped strings.

    Args:
        value: Either a comma-separated string or already a list.

    Returns:
        List of stripped, non-empty strings.
    """
    if isinstance(value, list):
        return [s.strip() for s in value if s.strip()]
    return [s.strip() for s in str(value).split(",") if s.strip()]
