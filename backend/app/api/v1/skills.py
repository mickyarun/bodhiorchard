# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Knowledge search and developer skill profile endpoints.

Scan-trigger / status / cancel routes have moved to
``app.api.v1.scans`` (mounted at ``/v1/reposcanv2/scans``).
"""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.knowledge_item import KnowledgeItem
from app.models.user import User
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.skills import (
    KnowledgeItemPage,
    KnowledgeItemRead,
    ModuleSkill,
    SkillProfileRead,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["skills"])


@router.get("/profiles", response_model=list[SkillProfileRead])
async def list_profiles(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SkillProfileRead]:
    """List all developer skill profiles for the organization.

    Groups skill entries by user and returns module-level detail.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of SkillProfileRead with per-module skill scores.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    sp_repo = SkillProfileRepository(db, org_id=org.id)
    rows = await sp_repo.list_with_users()

    # Group by user
    profiles_map: dict[str, SkillProfileRead] = {}
    for profile, user in rows:
        key = str(profile.user_id) if profile.user_id else profile.module
        if key not in profiles_map:
            profiles_map[key] = SkillProfileRead(
                userId=profile.user_id,
                userName=user.name if user else "Unknown",
                email=user.email if user else "",
                modules=[],
            )
        profiles_map[key].modules.append(
            ModuleSkill(
                name=profile.module,
                score=float(profile.skill_score),
                languages=profile.languages or [],
                touchCount=profile.touch_count,
            )
        )

    return list(profiles_map.values())


@router.get("/knowledge/{item_id}", response_model=KnowledgeItemRead)
async def get_knowledge_item(
    item_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeItemRead:
    """Fetch a single knowledge item by ID.

    Args:
        item_id: UUID of the knowledge item.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        KnowledgeItemRead for the requested item.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    item = await ki_repo.get_active_by_id(item_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Knowledge item not found.",
        )
    return KnowledgeItemRead(
        id=item.id,
        title=item.title,
        content=item.content,
        category=item.category,
        tags=item.tags,
        source=item.source,
        sourceRef=item.source_ref,
        featureStatus=item.feature_status,
        repoIds=[link.repo_id for link in item.repo_links],
    )


def _item_to_read(item: KnowledgeItem) -> KnowledgeItemRead:
    """Convert a KnowledgeItem ORM instance to API response schema."""
    return KnowledgeItemRead(
        id=item.id,
        title=item.title,
        content=item.content,
        category=item.category,
        tags=item.tags,
        source=item.source,
        sourceRef=item.source_ref,
        featureStatus=item.feature_status,
        repoIds=[link.repo_id for link in item.repo_links],
    )


@router.get("/knowledge", response_model=KnowledgeItemPage)
async def list_knowledge(
    category: str | None = Query(None, description="Filter by category"),
    repo_id: uuid.UUID | None = Query(
        None, description="Filter by tracked repository", alias="repoId"
    ),
    q: str | None = Query(
        None, description="Case-insensitive title substring filter", max_length=200
    ),
    limit: int = Query(24, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeItemPage:
    """List knowledge items for the organization with pagination and title search.

    Args:
        category: Optional category filter.
        repo_id: Optional tracked repository filter (via junction table).
        q: Optional case-insensitive substring match against title.
        limit: Maximum number of items to return.
        offset: Number of rows to skip (pagination).
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        KnowledgeItemPage with items for the current page plus the total count.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    title_query = q.strip() if q and q.strip() else None
    items = await ki_repo.list_active(
        category=category,
        repo_id=repo_id,
        title_query=title_query,
        limit=limit,
        offset=offset,
    )
    total = await ki_repo.count_active(
        category=category,
        repo_id=repo_id,
        title_query=title_query,
    )

    return KnowledgeItemPage(items=[_item_to_read(item) for item in items], total=total)


@router.get("/index-stats")
async def get_index_stats(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Return current knowledge index statistics.

    Combines org config (last scan info) with live counts from the database.

    Args:
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Dict with last scan info, knowledge item counts, and profile count.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    config = org.config or {}
    knowledge_cfg = config.get("knowledge", {})
    last_scan = knowledge_cfg.get("last_scan")

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    category_counts = await ki_repo.count_by_category()
    embedded_count = await ki_repo.count_embedded()

    sp_repo = SkillProfileRepository(db, org_id=org.id)
    profile_count = await sp_repo.count_profiles()

    # Count repos from tracked_repositories table (not title parsing)
    tr_repo = TrackedRepoRepository(db, org_id=org.id)
    active_repos = await tr_repo.list_active()
    repos_tracked = len(active_repos)

    return {
        "lastScan": last_scan,
        "knowledgeItems": {
            "total": sum(category_counts.values()),
            "byCategory": category_counts,
            "embedded": embedded_count,
        },
        "skillProfiles": profile_count,
        "reposTracked": repos_tracked,
    }
