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

"""Agent skill management endpoints.

Two parallel access modes:
* **slug-based** — used by the existing SettingsAgentPrompts UI to edit
  one skill at a time; updates fan out across every ``agent_type`` row
  sharing the slug (preserves the original "edit the product-manager
  prompt once" UX after the multi-agent-type split).
* **id-based** — new endpoints for the custom-skill workflow (create,
  delete, set-default).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.agent_skill import AgentSkill, AgentType
from app.models.user import User
from app.repositories.agent_skill import AgentSkillRepository
from app.schemas.agent_skills import (
    AgentSkillRead,
    AgentSkillUpdate,
    CustomSkillCreate,
)
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
    """True if the DB prompt differs from the file-based seed default."""
    try:
        file_skill = load_skill(slug)
        return db_prompt != file_skill.prompt
    except (FileNotFoundError, ValueError):
        return True


def _skill_to_read(skill_row: AgentSkill) -> AgentSkillRead:
    """Serialize a DB skill row, including agent_type / default / custom flags."""
    return AgentSkillRead(
        id=skill_row.id,
        skill_slug=skill_row.skill_slug,
        agent_type=skill_row.agent_type,
        is_default=skill_row.is_default,
        is_custom=skill_row.is_custom,
        name=skill_row.name,
        description=skill_row.description,
        tools=skill_row.tools,
        mcp_tools=skill_row.mcp_tools,
        prompt=skill_row.prompt,
        max_turns=getattr(skill_row, "max_turns", 0) or 0,
        timeout_seconds=getattr(skill_row, "timeout_seconds", 0) or 0,
        model=getattr(skill_row, "model", "") or "",
        iteration_model=getattr(skill_row, "iteration_model", "") or "",
        effort=getattr(skill_row, "effort", "") or "",
        is_customized=_check_customized(skill_row.prompt, skill_row.skill_slug),
    )


def _load_skill_or_raise(slug: str) -> Skill:
    """Load a file-defined skill, raising HTTPException on errors."""
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
    agent_type: AgentType | None = Query(default=None, description="Filter to one agent type"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[AgentSkillRead]:
    """List agent skills for the current org.

    On first call (no rows yet) seeds the file defaults. Optionally
    filters to a single ``agent_type``.
    """
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    skills = await repo.list_all()
    if not skills and list_available_skills():
        try:
            await seed_skills_for_org(current_user.org_id, db)
        except Exception:
            logger.exception("seed_skills_failed", org_id=str(current_user.org_id))
        skills = await repo.list_all()

    if agent_type is not None:
        skills = [s for s in skills if s.agent_type == agent_type]

    return [_skill_to_read(s) for s in skills]


@router.get(
    "/{slug}",
    response_model=AgentSkillRead,
    dependencies=[Depends(require_permissions("settings:view"))],
)
async def get_agent_skill(
    slug: str = _SLUG_PATH,
    agent_type: AgentType | None = Query(
        default=None,
        description="Disambiguate shared slugs (e.g. product-manager)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentSkillRead:
    """Get one skill by slug; ``agent_type`` is required for shared slugs."""
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    skill_row = await repo.get_by_slug(slug, agent_type=agent_type)
    if skill_row:
        return _skill_to_read(skill_row)

    # Fall back to file default — same shape, no DB row.
    skill = _load_skill_or_raise(slug)
    # File-based skills don't know their agent_type; require the caller
    # to provide it so the response is well-typed.
    if agent_type is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Skill not in DB yet; pass ?agent_type= to read the file "
                "default with a typed response"
            ),
        )
    return AgentSkillRead.from_skill(slug, skill, agent_type=agent_type)


@router.put(
    "/{slug}",
    response_model=AgentSkillRead,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def update_agent_skill(
    body: AgentSkillUpdate,
    slug: str = _SLUG_PATH,
    agent_type: AgentType | None = Query(
        default=None,
        description=(
            "Required when slug is shared across agent types (product-manager, "
            "testing). For unique slugs, the single matching row is updated."
        ),
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentSkillRead:
    """Update the (slug, agent_type) row. Partial-update semantics."""
    repo = AgentSkillRepository(db, org_id=current_user.org_id)

    existing = await repo.get_by_slug(slug, agent_type=agent_type)
    if existing is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skill not found: slug={slug}, agent_type={agent_type}",
        )

    if body.name is not None:
        existing.name = body.name
    if body.description is not None:
        existing.description = body.description
    if body.tools is not None:
        existing.tools = body.tools
    if body.mcp_tools is not None:
        existing.mcp_tools = body.mcp_tools
    if body.prompt is not None:
        existing.prompt = body.prompt
    if body.max_turns is not None:
        existing.max_turns = body.max_turns
    if body.timeout_seconds is not None:
        existing.timeout_seconds = body.timeout_seconds
    if body.model is not None:
        existing.model = body.model
    if body.iteration_model is not None:
        existing.iteration_model = body.iteration_model
    if body.effort is not None:
        existing.effort = body.effort

    await db.flush()
    await db.refresh(existing)

    logger.info(
        "agent_skill_updated",
        slug=slug,
        agent_type=str(existing.agent_type),
        org_id=str(current_user.org_id),
    )
    return _skill_to_read(existing)


@router.delete(
    "/{slug}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def reset_agent_skill(
    slug: str = _SLUG_PATH,
    agent_type: AgentType | None = Query(default=None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Reset a seeded skill back to its file default.

    Custom skills are NOT reset by this endpoint — use ``DELETE /{id}``
    to remove a custom skill instead.
    """
    file_skill = _load_skill_or_raise(slug)
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    existing = await repo.get_by_slug(slug, agent_type=agent_type)
    if existing is None or existing.is_custom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Seeded skill not found for that slug/agent_type",
        )

    existing.name = file_skill.name
    existing.description = file_skill.description
    existing.tools = file_skill.tools
    existing.mcp_tools = file_skill.mcp_tools
    existing.prompt = file_skill.prompt
    existing.max_turns = file_skill.max_turns
    existing.timeout_seconds = file_skill.timeout_seconds
    existing.model = file_skill.model
    existing.iteration_model = file_skill.iteration_model
    existing.effort = file_skill.effort
    await db.flush()

    logger.info(
        "agent_skill_reset",
        slug=slug,
        agent_type=str(existing.agent_type),
        org_id=str(current_user.org_id),
    )


# ────────────────────────────── Custom skill CRUD ──────────────────────────────


@router.post(
    "/",
    response_model=AgentSkillRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def create_custom_skill(
    body: CustomSkillCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentSkillRead:
    """Create a user-authored skill tied to ``agent_type``.

    The (slug, agent_type) pair must be unique within the org. Newly
    created skills are NOT marked default — call ``POST /{id}/set-default``
    to promote one explicitly.
    """
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    if await repo.get_by_slug(body.skill_slug, agent_type=body.agent_type):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"A skill with slug '{body.skill_slug}' already exists for "
                f"agent_type '{body.agent_type.value}'"
            ),
        )
    created = await repo.create_custom(
        skill_slug=body.skill_slug,
        agent_type=body.agent_type,
        name=body.name,
        description=body.description,
        tools=body.tools,
        mcp_tools=body.mcp_tools,
        prompt=body.prompt,
        max_turns=body.max_turns,
        timeout_seconds=body.timeout_seconds,
        model=body.model,
        iteration_model=body.iteration_model,
        effort=body.effort,
    )
    logger.info(
        "custom_skill_created",
        skill_id=str(created.id),
        slug=created.skill_slug,
        agent_type=str(created.agent_type),
        org_id=str(current_user.org_id),
    )
    return _skill_to_read(created)


@router.post(
    "/{skill_id}/set-default",
    response_model=AgentSkillRead,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def set_default_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> AgentSkillRead:
    """Mark a skill as default for its agent_type (demoting the prior default)."""
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    try:
        updated = await repo.set_default(skill_id)
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(err)) from err
    logger.info(
        "agent_skill_default_set",
        skill_id=str(updated.id),
        agent_type=str(updated.agent_type),
        org_id=str(current_user.org_id),
    )
    return _skill_to_read(updated)


@router.delete(
    "/by-id/{skill_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("settings:edit"))],
)
async def delete_custom_skill(
    skill_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a custom skill. Returns 409 for seeded skills."""
    repo = AgentSkillRepository(db, org_id=current_user.org_id)
    existing = await repo.get_by_id(skill_id)
    if existing is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found")
    if not existing.is_custom:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Seeded skills cannot be deleted; use PUT to reset to file default",
        )
    deleted = await repo.delete_custom(skill_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Skill not found or not custom"
        )
    logger.info(
        "custom_skill_deleted",
        skill_id=str(skill_id),
        org_id=str(current_user.org_id),
    )
