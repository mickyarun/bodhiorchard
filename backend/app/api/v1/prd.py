"""PRD CRUD endpoints."""

import uuid

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.prd import PRDDocument, PRDStatus
from app.models.user import User
from app.schemas.prd import PRDCreate, PRDListItem, PRDRead, PRDUpdate

logger = structlog.get_logger(__name__)

router = APIRouter(tags=["prds"])


@router.get(
    "/",
    response_model=list[PRDListItem],
    dependencies=[Depends(require_permissions("prds:view"))],
)
async def list_prds(
    status_filter: str | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[PRDDocument]:
    """List PRDs for the current user's organization.

    Args:
        status_filter: Optional status to filter by.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        A list of PRD summary items.
    """
    query = (
        select(PRDDocument)
        .where(PRDDocument.org_id == current_user.org_id)
        .order_by(PRDDocument.prd_number.desc())
    )

    if status_filter:
        try:
            PRDStatus(status_filter)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {status_filter}",
            ) from None
        query = query.where(PRDDocument.status == status_filter)

    result = await db.execute(query)
    return list(result.scalars().all())


@router.post(
    "/",
    response_model=PRDRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("prds:create"))],
)
async def create_prd(
    body: PRDCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PRDDocument:
    """Create a new PRD with auto-incremented prd_number.

    Args:
        body: PRD creation data.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The newly created PRD document.
    """
    max_result = await db.execute(
        select(func.coalesce(func.max(PRDDocument.prd_number), 0)).where(
            PRDDocument.org_id == current_user.org_id
        )
    )
    next_number = max_result.scalar_one() + 1

    prd = PRDDocument(
        org_id=current_user.org_id,
        prd_number=next_number,
        title=body.title,
        status=PRDStatus.DRAFT,
        content_md=body.content_md,
        metadata_=body.metadata_,
    )
    db.add(prd)
    await db.flush()
    await db.refresh(prd)

    logger.info("prd_created", prd_id=str(prd.id), prd_number=next_number, org_id=str(prd.org_id))

    return prd


@router.get(
    "/{prd_id}",
    response_model=PRDRead,
    dependencies=[Depends(require_permissions("prds:view"))],
)
async def get_prd(
    prd_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PRDDocument:
    """Retrieve a single PRD by ID.

    Args:
        prd_id: The PRD UUID.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The requested PRD document.

    Raises:
        HTTPException: If the PRD is not found or belongs to another org.
    """
    result = await db.execute(
        select(PRDDocument).where(
            PRDDocument.id == prd_id,
            PRDDocument.org_id == current_user.org_id,
        )
    )
    prd = result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRD not found")
    return prd


@router.patch(
    "/{prd_id}",
    response_model=PRDRead,
    dependencies=[Depends(require_permissions("prds:edit"))],
)
async def update_prd(
    prd_id: uuid.UUID,
    body: PRDUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PRDDocument:
    """Update a PRD (title, status, content, tech spec, test plan, metadata).

    Args:
        prd_id: The PRD UUID.
        body: Fields to update.
        current_user: The authenticated user.
        db: The async database session.

    Returns:
        The updated PRD document.

    Raises:
        HTTPException: If the PRD is not found or status is invalid.
    """
    result = await db.execute(
        select(PRDDocument).where(
            PRDDocument.id == prd_id,
            PRDDocument.org_id == current_user.org_id,
        )
    )
    prd = result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRD not found")

    update_data = body.model_dump(exclude_unset=True)

    if "status" in update_data:
        try:
            update_data["status"] = PRDStatus(update_data["status"])
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status: {update_data['status']}",
            ) from None

    for field, value in update_data.items():
        setattr(prd, field, value)

    await db.flush()
    await db.refresh(prd)

    logger.info("prd_updated", prd_id=str(prd.id), fields=list(update_data.keys()))

    return prd


@router.delete(
    "/{prd_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_permissions("backlog:delete"))],
)
async def delete_prd(
    prd_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete a PRD.

    Args:
        prd_id: The PRD UUID.
        current_user: The authenticated user.
        db: The async database session.

    Raises:
        HTTPException: If the PRD is not found.
    """
    result = await db.execute(
        select(PRDDocument).where(
            PRDDocument.id == prd_id,
            PRDDocument.org_id == current_user.org_id,
        )
    )
    prd = result.scalar_one_or_none()
    if prd is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="PRD not found")

    await db.delete(prd)
    logger.info("prd_deleted", prd_id=str(prd.id))
