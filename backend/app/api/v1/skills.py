# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Skill scanning, knowledge search, and developer profile endpoints."""

import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
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
    ScanRequest,
    ScanResponse,
    ScanStatus,
    SkillProfileRead,
)
from app.services.scan_pipeline import run_scan_pipeline
from app.services.scan_progress import (
    create_scan_progress,
    enrich_status_with_phases,
    resolve_scan_progress,
)

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["skills"])


@router.post(
    "/scan",
    response_model=ScanResponse,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def trigger_scan(
    body: ScanRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanResponse:
    """Trigger a full repository scan as a background task.

    Validates that the org has a configured source code path with a .git directory,
    then kicks off GitNexus indexing, doc extraction, skill analysis, and embedding.

    Args:
        body: Scan request with optional full_rescan flag.
        background_tasks: FastAPI background task manager.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        ScanResponse with a scan_id to poll for status.
    """
    # Gate: verify embedding service is healthy before scanning
    from app.services.embedding_service import embedding_service

    embed_ok, embed_err = await embedding_service.check()
    if not embed_ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Embedding service unavailable: {embed_err}. Cannot scan.",
        )

    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    # Read active repos from the tracked_repositories table
    repo_repo = TrackedRepoRepository(db, org_id=org.id)

    # Gate: require both main and develop branches mapped for all active repos
    active_repos = await repo_repo.list_active()
    unmapped_main = [r.name for r in active_repos if not r.main_branch]
    unmapped_dev = [r.name for r in active_repos if not r.develop_branch]
    unmapped = sorted(set(unmapped_main + unmapped_dev))
    if unmapped:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Map branches before scanning. Unmapped: {', '.join(unmapped)}",
        )

    repo_paths = await repo_repo.get_active_paths()

    if not repo_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No repositories tracked. Add repos in Settings.",
        )

    # Validate paths still exist on disk
    valid_paths: list[str] = []
    for rp in repo_paths:
        if Path(rp).exists() and (Path(rp) / ".git").exists():
            valid_paths.append(rp)
        else:
            logger.warning("scan_skip_missing_repo", path=rp)

    if not valid_paths:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="None of the tracked repositories exist on disk.",
        )
    repo_paths = valid_paths

    # A full rescan is the user saying "ignore any SHA shortcuts —
    # rebuild this org from scratch". Clearing ``head_sha`` +
    # ``last_scanned_at`` is what tells ``phase_a_scan_mode`` to treat
    # every active repo as a first-time index. The dedicated
    # ``/scan/reset`` endpoint does the same via
    # ``TrackedRepoRepository.reset_head_shas``; keep the two dispatch
    # paths consistent so users don't have to reach for Reset just to
    # defeat the incremental shortcut.
    if body.full_rescan:
        cleared = await repo_repo.reset_head_shas()
        await db.commit()
        logger.info(
            "scan_full_rescan_cleared_shas",
            org_id=str(org.id),
            repos_cleared=cleared,
        )

    scan_id = str(uuid.uuid4())
    await create_scan_progress(scan_id, str(org.id))

    background_tasks.add_task(
        run_scan_pipeline,
        scan_id=scan_id,
        org_id=org.id,
        repo_paths=repo_paths,
        full_rescan=body.full_rescan,
        user_id=str(current_user.id),
    )

    return ScanResponse(scanId=scan_id, status="started")


@router.get("/scan/{scan_id}/status", response_model=ScanStatus)
async def get_scan_status(
    scan_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ScanStatus:
    """Poll the status of a running or completed scan.

    Falls back to the org's currently-active scan if the direct lookup
    misses — so a browser tab switch that briefly drops the WS doesn't
    surface a phantom 404 mid-scan.

    Args:
        scan_id: The scan ID returned by POST /scan.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        ScanStatus with progress percentage and results.
    """
    org = await OrganizationRepository(db).get_for_user(current_user)
    scan_progress = await resolve_scan_progress(scan_id, str(org.id))
    if scan_progress is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan not found: {scan_id}",
        )
    return await enrich_status_with_phases(db, org.id, scan_progress)


@router.post(
    "/scan/{scan_id}/cancel",
    response_model=ScanStatus,
    dependencies=[Depends(require_permissions("org:edit_settings"))],
)
async def cancel_scan_endpoint(
    scan_id: str,
    current_user: User = Depends(get_current_user),
) -> ScanStatus:
    """Cancel a running scan, marking it as failed.

    Args:
        scan_id: The scan ID to cancel.
        current_user: The authenticated user.

    Returns:
        Updated ScanStatus with status='failed'.
    """
    from app.services.scan_progress import cancel_scan

    result = await cancel_scan(scan_id)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan not found: {scan_id}",
        )
    return result


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
