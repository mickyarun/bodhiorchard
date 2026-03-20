"""Skill scanning, knowledge search, and developer profile endpoints."""

import re
import uuid
from pathlib import Path

import structlog
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.knowledge_item import KnowledgeItemRepository
from app.repositories.organization import OrganizationRepository
from app.repositories.skill_profile import SkillProfileRepository
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.skills import (
    KnowledgeItemRead,
    KnowledgeSearchRequest,
    KnowledgeSearchResult,
    ModuleSkill,
    ScanRequest,
    ScanResponse,
    ScanStatus,
    SkillProfileRead,
)
from app.services.embedding_service import embedding_service
from app.services.scan_pipeline import run_scan_pipeline, scan_statuses

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["skills"])


@router.post("/scan", response_model=ScanResponse)
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
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    # Read active repos from the tracked_repositories table
    repo_repo = TrackedRepoRepository(db, org_id=org.id)
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

    scan_id = str(uuid.uuid4())
    scan_status = ScanStatus(scanId=scan_id, status="started", progressPct=0)
    scan_statuses[scan_id] = scan_status

    background_tasks.add_task(
        run_scan_pipeline,
        scan_id=scan_id,
        org_id=org.id,
        repo_paths=repo_paths,
        full_rescan=body.full_rescan,
    )

    return ScanResponse(scanId=scan_id, status="started")


@router.get("/scan/{scan_id}/status", response_model=ScanStatus)
async def get_scan_status(
    scan_id: str,
    current_user: User = Depends(get_current_user),
) -> ScanStatus:
    """Poll the status of a running or completed scan.

    Args:
        scan_id: The scan ID returned by POST /scan.
        current_user: The authenticated user.

    Returns:
        ScanStatus with progress percentage and results.
    """
    scan_status = scan_statuses.get(scan_id)
    if scan_status is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Scan not found: {scan_id}",
        )
    return scan_status


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
        repoId=item.repo_id,
    )


@router.get("/knowledge", response_model=list[KnowledgeItemRead])
async def list_knowledge(
    category: str | None = Query(None, description="Filter by category"),
    repo_id: uuid.UUID | None = Query(
        None, description="Filter by tracked repository", alias="repoId"
    ),
    limit: int = Query(50, ge=1, le=200),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeItemRead]:
    """List knowledge items for the organization.

    Args:
        category: Optional category filter.
        repo_id: Optional tracked repository filter.
        limit: Maximum number of items to return.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of KnowledgeItemRead objects.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)
    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    items = await ki_repo.list_active(category=category, repo_id=repo_id, limit=limit)

    return [
        KnowledgeItemRead(
            id=item.id,
            title=item.title,
            content=item.content,
            category=item.category,
            tags=item.tags,
            source=item.source,
            sourceRef=item.source_ref,
            featureStatus=item.feature_status,
            repoId=item.repo_id,
        )
        for item in items
    ]


@router.post("/knowledge/search", response_model=list[KnowledgeSearchResult])
async def search_knowledge(
    body: KnowledgeSearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeSearchResult]:
    """Semantic search over knowledge items using pgvector.

    Embeds the query, then finds nearest neighbors in the knowledge_items table.

    Args:
        body: Search request with query text and optional filters.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        List of KnowledgeSearchResult objects ranked by similarity.
    """
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_for_user(current_user)

    try:
        query_vector = await embedding_service.embed(body.query)
    except Exception as exc:
        logger.exception("knowledge_search_embed_failed", query=body.query[:100])
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Embedding service unavailable. Check your AI configuration.",
        ) from exc

    ki_repo = KnowledgeItemRepository(db, org_id=org.id)
    rows = await ki_repo.semantic_search(query_vector, category=body.category, limit=body.limit)

    return [
        KnowledgeSearchResult(
            title=item.title,
            content=item.content or "",
            category=item.category,
            score=round(1.0 - distance, 4),
            sourceRef=item.source_ref,
            featureStatus=item.feature_status,
        )
        for item, distance in rows
    ]


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

    # Count distinct repos from knowledge item titles ([RepoName] prefix)
    titles = await ki_repo.list_titles_with_prefix("[%]%")
    repo_names: set[str] = set()
    for title in titles:
        m = re.match(r"^\[([^\]]+)\]", title)
        if m:
            repo_names.add(m.group(1))
    if repo_names:
        repos_tracked = len(repo_names)
    else:
        repos_tracked = min(len(knowledge_cfg.get("repo_shas", {})), 1)

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
