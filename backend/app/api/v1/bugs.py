"""Bug CRUD endpoints — create, list, get, update."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bug import Bug, BugStatus
from app.models.user import User
from app.repositories.bug import BugRepository
from app.repositories.user import UserRepository
from app.schemas.bug import (
    BugCreate,
    BugListItem,
    BugListResponse,
    BugRead,
    BugUpdate,
)

router = APIRouter(tags=["bugs"])


@router.post(
    "",
    response_model=BugRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def create_bug(
    body: BugCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugRead:
    """Create a new bug report, optionally linked to a BUD."""
    bud_uuid = uuid.UUID(body.bud_id) if body.bud_id else None

    bug = Bug(
        org_id=current_user.org_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        module=body.module,
        bud_id=bud_uuid,
        reporter_id=current_user.id,
    )

    bug_repo = BugRepository(db, org_id=current_user.org_id)
    bug = await bug_repo.create(bug)

    # Generate embedding + auto-link in the background (non-blocking)
    _schedule_embedding_and_link(bug.id, current_user.org_id)

    return await _bug_to_read(db, bug, current_user.org_id)


@router.get(
    "",
    response_model=BugListResponse,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def list_bugs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = None,
    bud_id: str | None = Query(None, alias="budId"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
) -> BugListResponse:
    """List bugs with optional filters and pagination."""
    bug_repo = BugRepository(db, org_id=current_user.org_id)
    bud_uuid = uuid.UUID(bud_id) if bud_id else None
    items, total = await bug_repo.list_filtered(
        status=status_filter,
        severity=severity,
        bud_id=bud_uuid,
        page=page,
        page_size=page_size,
    )

    # Batch-resolve names
    user_ids: set[uuid.UUID] = set()
    bud_ids: set[uuid.UUID] = set()
    for b in items:
        user_ids.add(b.reporter_id)
        if b.assignee_id:
            user_ids.add(b.assignee_id)
        if b.bud_id:
            bud_ids.add(b.bud_id)

    user_names = await _resolve_user_names(db, current_user.org_id, user_ids)
    bud_info = await _resolve_bud_info(db, current_user.org_id, bud_ids)

    return BugListResponse(
        items=[
            BugListItem(
                id=str(b.id),
                title=b.title,
                severity=b.severity.value,
                status=b.status.value,
                module=b.module,
                bud_id=str(b.bud_id) if b.bud_id else None,
                bud_number=bud_info.get(b.bud_id, {}).get("number") if b.bud_id else None,
                reporter_name=user_names.get(b.reporter_id),
                assignee_name=user_names.get(b.assignee_id) if b.assignee_id else None,
                created_at=b.created_at,
            )
            for b in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{bug_id}",
    response_model=BugRead,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_bug(
    bug_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugRead:
    """Get a single bug by ID."""
    bug_repo = BugRepository(db, org_id=current_user.org_id)
    bug = await bug_repo.get_by_id(bug_id)
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")
    return await _bug_to_read(db, bug, current_user.org_id)


@router.patch(
    "/{bug_id}",
    response_model=BugRead,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def update_bug(
    bug_id: uuid.UUID,
    body: BugUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugRead:
    """Update a bug (status, assignee, severity, link to BUD, etc.)."""
    bug_repo = BugRepository(db, org_id=current_user.org_id)
    bug = await bug_repo.get_by_id(bug_id)
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")

    update = body.model_dump(exclude_unset=True, by_alias=False)
    if "bud_id" in update:
        update["bud_id"] = uuid.UUID(update["bud_id"]) if update["bud_id"] else None
    if "assignee_id" in update:
        update["assignee_id"] = uuid.UUID(update["assignee_id"]) if update["assignee_id"] else None

    # Set resolved_at when transitioning to resolved/closed
    if (
        "status" in update
        and update["status"] in (BugStatus.RESOLVED, BugStatus.CLOSED)
        and not bug.resolved_at
    ):
        from datetime import UTC, datetime

        update["resolved_at"] = datetime.now(UTC)

    for field, value in update.items():
        setattr(bug, field, value)
    await db.flush()
    await db.refresh(bug)

    return await _bug_to_read(db, bug, current_user.org_id)


# ── Helpers ──────────────────────────────────────────────────────────


def _schedule_embedding_and_link(bug_id: uuid.UUID, org_id: uuid.UUID) -> None:
    """Fire-and-forget: generate embedding + auto-link to closest BUD."""
    import asyncio

    task = asyncio.create_task(
        _bg_embed_and_link(bug_id, org_id),
        name=f"bug_embed_{bug_id}",
    )
    task.add_done_callback(
        lambda t: t.result() if not t.cancelled() and not t.exception() else None,
    )


async def _bg_embed_and_link(bug_id: uuid.UUID, org_id: uuid.UUID) -> None:
    """Background: embed bug text and auto-link to closest BUD."""
    import structlog

    from app.database import AsyncSessionLocal

    logger = structlog.get_logger(__name__)
    try:
        async with AsyncSessionLocal() as db:
            bug_repo = BugRepository(db, org_id=org_id)
            bug = await bug_repo.get_by_id(bug_id)
            if not bug:
                return

            from app.services.bug_linker import embed_and_link_bug

            await embed_and_link_bug(db, org_id, bug)
            await db.commit()
    except Exception:
        logger.warning("bug_embed_link_failed", bug_id=str(bug_id), exc_info=True)


async def _bug_to_read(
    db: AsyncSession,
    bug: Bug,
    org_id: uuid.UUID,
) -> BugRead:
    """Convert a Bug ORM instance to a BugRead response with resolved names."""
    user_ids = {bug.reporter_id}
    if bug.assignee_id:
        user_ids.add(bug.assignee_id)
    user_names = await _resolve_user_names(db, org_id, user_ids)

    bud_number = None
    bud_title = None
    if bug.bud_id:
        bud_info = await _resolve_bud_info(db, org_id, {bug.bud_id})
        info = bud_info.get(bug.bud_id, {})
        bud_number = info.get("number")
        bud_title = info.get("title")

    return BugRead(
        id=str(bug.id),
        title=bug.title,
        description=bug.description,
        severity=bug.severity.value,
        status=bug.status.value,
        module=bug.module,
        linked_pr=bug.linked_pr,
        bud_id=str(bug.bud_id) if bug.bud_id else None,
        bud_number=bud_number,
        bud_title=bud_title,
        reporter_id=str(bug.reporter_id),
        reporter_name=user_names.get(bug.reporter_id),
        assignee_id=str(bug.assignee_id) if bug.assignee_id else None,
        assignee_name=user_names.get(bug.assignee_id) if bug.assignee_id else None,
        resolved_at=bug.resolved_at,
        created_at=bug.created_at,
        updated_at=bug.updated_at,
    )


async def _resolve_user_names(
    db: AsyncSession,
    org_id: uuid.UUID,
    user_ids: set[uuid.UUID],
) -> dict[uuid.UUID, str]:
    """Batch-resolve user IDs to display names."""
    if not user_ids:
        return {}
    user_repo = UserRepository(db, org_id=org_id)
    return await user_repo.get_names_by_ids(user_ids)


async def _resolve_bud_info(
    db: AsyncSession,
    org_id: uuid.UUID,
    bud_ids: set[uuid.UUID],
) -> dict[uuid.UUID, dict]:
    """Batch-resolve BUD IDs to {number, title} dicts."""
    if not bud_ids:
        return {}
    from sqlalchemy import select

    from app.models.bud import BUDDocument

    stmt = (
        select(BUDDocument.id, BUDDocument.bud_number, BUDDocument.title)
        .where(BUDDocument.org_id == org_id, BUDDocument.id.in_(bud_ids))
    )
    result = await db.execute(stmt)
    return {
        row.id: {"number": row.bud_number, "title": row.title}
        for row in result.all()
    }
