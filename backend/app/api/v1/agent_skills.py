"""Agent skill management endpoints."""

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.agent_skill import AgentSkill
from app.models.user import User
from app.repositories.agent_skill import AgentSkillRepository
from app.schemas.agent_skills import AgentSkillRead, AgentSkillUpdate
from app.services.skill_loader import (
    Skill,
    list_available_skills,
    load_skill,
    seed_skills_for_org,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["agent-skills"])

_SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9\-]{0,98}[a-z0-9])?$"
_SLUG_PATH = Path(..., pattern=_SLUG_PATTERN, description="Skill slug (kebab-case)")


def _check_customized(db_prompt: str, slug: str) -> bool:
    """Compare a DB skill prompt against the file-based seed default.

    Args:
        db_prompt: The prompt stored in the DB.
        slug: The skill slug to load the file default for.

    Returns:
        True if the DB version differs from the file default (or file is unavailable).
    """
    try:
        file_skill = load_skill(slug)
        return db_prompt != file_skill.prompt
    except (FileNotFoundError, ValueError):
        return True


def _skill_to_read(slug: str, skill_row: AgentSkill) -> AgentSkillRead:
    """Convert a DB skill row to an AgentSkillRead schema."""
    return AgentSkillRead(
        skill_slug=slug,
        name=skill_row.name,
        description=skill_row.description,
        tools=skill_row.tools,
        mcp_tools=skill_row.mcp_tools,
        prompt=skill_row.prompt,
        max_turns=getattr(skill_row, "max_turns", 0) or 0,
        model=getattr(skill_row, "model", "") or "",
        effort=getattr(skill_row, "effort", "") or "",
        is_customized=_check_customized(skill_row.prompt, slug),
    )


def _load_skill_or_raise(slug: str) -> Skill:
    """Load a skill from file, raising HTTPException on failure.

    Args:
        slug: The skill slug.

    Returns:
        The loaded Skill.

    Raises:
        HTTPException: 404 if file not found, 422 if file is malformed.
    """
    try:
        return load_skill(slug)
    except FileNotFoundError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Skill not found: {slug}"
        ) from err
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Skill file is malformed for '{slug}': {err}",
        ) from err


@router.get(
    "/",
    response_model=list[AgentSkillRead],
    dependencies=[Depends(require_permissions("settings:view"))],
)
async def list_agent_skills(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentSkillRead]:
    """List all agent skills merged from file defaults and DB overrides.

    On first call for an org (no overrides exist), seeds defaults from files.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of all skills with is_customized flag.
    """
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    skills = await repo.list_all()

    # Lazy seed: if no skills at all and skills directory has files, seed once
    if not skills and list_available_skills():
        try:
            await seed_skills_for_org(current_user.org_id, db)
        except Exception:
            logger.exception("seed_skills_failed", org_id=str(current_user.org_id))
        skills = await repo.list_all()

    skill_map = {s.skill_slug: s for s in skills}
    available_slugs = list_available_skills()

    # Build merged list: DB skills marked customized, file defaults as-is
    all_slugs = sorted(set(available_slugs) | set(skill_map.keys()))
    result: list[AgentSkillRead] = []

    for slug in all_slugs:
        if slug in skill_map:
            result.append(_skill_to_read(slug, skill_map[slug]))
        else:
            try:
                skill = load_skill(slug)
                result.append(AgentSkillRead.from_skill(slug, skill))
            except (FileNotFoundError, ValueError, OSError):
                logger.warning("skill_file_load_failed", skill=slug)

    return result


@router.get(
    "/{slug}",
    response_model=AgentSkillRead,
    dependencies=[Depends(require_permissions("settings:view"))],
)
async def get_agent_skill(
    slug: str = _SLUG_PATH,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentSkillRead:
    """Get a single agent skill by slug.

    Args:
        slug: The skill slug (e.g. 'triage-analyst').
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The skill detail.

    Raises:
        HTTPException: If the skill slug doesn't exist anywhere.
    """
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    skill_row = await repo.get_by_slug(slug)

    if skill_row:
        return _skill_to_read(slug, skill_row)

    skill = _load_skill_or_raise(slug)
    return AgentSkillRead.from_skill(slug, skill)


@router.put(
    "/{slug}",
    response_model=AgentSkillRead,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def update_agent_skill(
    body: AgentSkillUpdate,
    slug: str = _SLUG_PATH,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentSkillRead:
    """Create or update a skill override for the current org.

    Partial updates are supported — only provided fields are changed.

    Args:
        slug: The skill slug.
        body: Fields to update.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The updated skill.
    """
    repo = AgentSkillRepository(db, org_id=current_user.org_id)

    # Load current state (DB override or file default) as base
    existing = await repo.get_by_slug(slug)
    if existing:
        name = body.name if body.name is not None else existing.name
        description = body.description if body.description is not None else existing.description
        tools = body.tools if body.tools is not None else existing.tools
        mcp_tools = body.mcp_tools if body.mcp_tools is not None else existing.mcp_tools
        prompt = body.prompt if body.prompt is not None else existing.prompt
        max_turns = body.max_turns if body.max_turns is not None else (existing.max_turns or 0)
        model = body.model if body.model is not None else (getattr(existing, "model", "") or "")
        effort = (
            body.effort if body.effort is not None else (getattr(existing, "effort", "") or "")
        )
    else:
        file_skill = _load_skill_or_raise(slug)
        name = body.name if body.name is not None else file_skill.name
        description = body.description if body.description is not None else file_skill.description
        tools = body.tools if body.tools is not None else file_skill.tools
        mcp_tools = body.mcp_tools if body.mcp_tools is not None else file_skill.mcp_tools
        prompt = body.prompt if body.prompt is not None else file_skill.prompt
        max_turns = body.max_turns if body.max_turns is not None else file_skill.max_turns
        model = body.model if body.model is not None else file_skill.model
        effort = body.effort if body.effort is not None else file_skill.effort

    updated = await repo.upsert(
        skill_slug=slug,
        name=name,
        description=description,
        tools=tools,
        mcp_tools=mcp_tools,
        prompt=prompt,
        max_turns=max_turns,
        model=model,
        effort=effort,
    )

    logger.info("agent_skill_updated", slug=slug, org_id=str(current_user.org_id))

    return _skill_to_read(slug, updated)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def reset_agent_skill(
    slug: str = _SLUG_PATH,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Reset a skill to its file default by deleting the DB override.

    Args:
        slug: The skill slug.
        current_user: The authenticated user.
        db: The async database session.

    Raises:
        HTTPException: If no override exists to reset.
    """
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    deleted = await repo.delete_by_slug(slug)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No custom override exists for skill: {slug}",
        )
    logger.info("agent_skill_reset", slug=slug, org_id=str(current_user.org_id))
