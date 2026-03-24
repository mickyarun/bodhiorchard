"""Living Tree Dashboard endpoints."""

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db
from app.models.user import User
from app.repositories.tracked_repository import TrackedRepoRepository
from app.schemas.dashboard import TreeData
from app.services.tree_data import get_tree_data

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["dashboard"])


@router.get("/tree-data", response_model=TreeData)
async def tree_data(
    refresh: bool = Query(False, description="Bypass the TTL cache"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> TreeData:
    """Return aggregated tree data for the Living Tree visualization.

    Collects data from git history, BUDs, bugs, agent logs, and member
    profiles. Results are cached for 5 minutes per organization.

    Args:
        refresh: If True, bypass the cache and rebuild data.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        Aggregated TreeData payload for the frontend renderer.
    """
    repo_repo = TrackedRepoRepository(db, org_id=current_user.org_id)
    tracked_repos = await repo_repo.get_active_path_name_pairs()

    tree = await get_tree_data(
        db,
        current_user.org_id,
        tracked_repos,
        refresh=refresh,
    )

    logger.info(
        "tree_data_served",
        org_id=str(current_user.org_id),
        repos=len(tree.repos),
        branches=len(tree.branches),
        members=len(tree.members),
        cached=not refresh,
    )

    return tree
