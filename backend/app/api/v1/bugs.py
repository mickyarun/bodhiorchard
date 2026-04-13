"""Bug CRUD endpoints — create, list, get, update."""

import asyncio
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

    # Auto-set bug_type based on the linked BUD's current status:
    # testing/code_review/development → "testing" (internal QA bug)
    # uat/prod/closed → "production" (post-release bug)
    bug_type = "testing"
    if bud_uuid:
        from app.repositories.bud import BUDRepository

        bud_repo_check = BUDRepository(db, org_id=current_user.org_id)
        linked = await bud_repo_check.get_by_id(bud_uuid)
        if linked and linked.status in ("uat", "prod", "closed"):
            bug_type = "production"

    bug = Bug(
        org_id=current_user.org_id,
        title=body.title,
        description=body.description,
        severity=body.severity,
        module=body.module,
        bud_id=bud_uuid,
        bug_type=bug_type,
        reporter_id=current_user.id,
    )

    bug_repo = BugRepository(db, org_id=current_user.org_id)
    bug = await bug_repo.create(bug)

    # Embed + auto-link inline so the response includes the linked BUD.
    # This is fast (~100ms embed + 1 pgvector query) and gives the user
    # immediate feedback about which BUD was matched.
    if not bud_uuid:
        try:
            from app.services.bug_linker import embed_and_link_bug

            await embed_and_link_bug(db, current_user.org_id, bug)
            # Always flush + refresh after embed_and_link_bug — it modifies
            # bug.embedding (and possibly bug.bud_id), which expires other
            # ORM attributes. Without refresh, accessing bug.updated_at in
            # _bug_to_read triggers a MissingGreenlet error.
            await db.flush()
            await db.refresh(bug)
        except Exception:
            import structlog

            structlog.get_logger(__name__).warning(
                "bug_embed_link_failed_inline", bug_id=str(bug.id), exc_info=True,
            )
    else:
        # BUD already linked manually — just generate embedding in background
        _schedule_embedding(bug.id, current_user.org_id)

    # If the bug is linked to a BUD that's in testing, check whether the
    # open bug count now exceeds the org's rejection threshold. If so, the
    # BUD auto-rejects back to development.
    linked_bud_id = bug.bud_id
    if linked_bud_id:
        try:
            from app.repositories.bud import BUDRepository
            from app.services.bug_testing_gate import check_bug_threshold

            bud_repo = BUDRepository(db, org_id=current_user.org_id)
            linked_bud = await bud_repo.get_by_id(linked_bud_id)
            if linked_bud:
                await check_bug_threshold(db, current_user.org_id, linked_bud)
                await db.flush()
        except Exception:
            import structlog

            structlog.get_logger(__name__).warning(
                "bug_threshold_check_failed", bug_id=str(bug.id), exc_info=True,
            )

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
                bug_type=b.bug_type.value,
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
        # Validate the target BUD belongs to this org (prevent cross-tenant leak)
        if update["bud_id"]:
            from app.repositories.bud import BUDRepository as BudRepoCheck

            bud_check = BudRepoCheck(db, org_id=current_user.org_id)
            if not await bud_check.get_by_id(update["bud_id"]):
                raise HTTPException(status_code=404, detail="BUD not found")
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


_background_tasks: set[asyncio.Task[None]] = set()


def _schedule_embedding(bug_id: uuid.UUID, org_id: uuid.UUID) -> None:
    """Fire-and-forget: generate embedding only (BUD already linked manually)."""
    task = asyncio.create_task(
        _bg_embed(bug_id, org_id),
        name=f"bug_embed_{bug_id}",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _bg_embed(bug_id: uuid.UUID, org_id: uuid.UUID) -> None:
    """Background: generate embedding for a bug (no auto-link)."""
    import structlog

    from app.database import AsyncSessionLocal

    logger = structlog.get_logger(__name__)
    try:
        async with AsyncSessionLocal() as db:
            bug_repo = BugRepository(db, org_id=org_id)
            bug = await bug_repo.get_by_id(bug_id)
            if not bug:
                return

            from app.services.embedding_service import embedding_service

            text = bug.title
            if bug.description:
                text = f"{text} {bug.description}"
            bug.embedding = await embedding_service.embed(text)
            await db.commit()
    except Exception:
        logger.warning("bug_embed_failed", bug_id=str(bug_id), exc_info=True)


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
        bug_type=bug.bug_type.value,
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
