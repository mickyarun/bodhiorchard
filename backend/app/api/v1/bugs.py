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

"""Bug CRUD endpoints — create, list, board, get, update."""

import asyncio
import uuid
from datetime import UTC, datetime

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._bug_serializers import bug_to_read, bugs_to_list_items
from app.core.deps import (
    get_current_user,
    get_db,
    get_user_permissions,
    require_permissions,
)
from app.database import AsyncSessionLocal
from app.models.bug import Bug, BugStatus, BugType
from app.models.user import User
from app.repositories.bud import BUDRepository
from app.repositories.bug import BugRepository
from app.repositories.feature import FeatureRepository
from app.schemas.bug import (
    BugBoardResponse,
    BugCreate,
    BugListItem,
    BugListResponse,
    BugRead,
    BugUpdate,
)
from app.services.bug_linker import embed_and_link_bug
from app.services.bug_testing_gate import check_bug_threshold
from app.services.embedding_service import embedding_service
from app.services.sp_qa import award_qa_sp_on_bug_status

logger = structlog.get_logger(__name__)
router = APIRouter(tags=["bugs"])


# ── Endpoints ────────────────────────────────────────────────────────


@router.post(
    "",
    response_model=BugRead,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    # TODO(step-e-cleanup): dual-gate for the migration window —
    # existing role tokens that still carry ``buds:edit`` keep working
    # while the new ``bugs:report`` rolls out via
    # :func:`app.services.permission_seeder.seed_permissions`. Drop the
    # legacy half once the seeder has run across all orgs (grep
    # ``TODO(step-e-cleanup)`` to find every site).
    dependencies=[Depends(require_permissions("bugs:report", "buds:edit", mode="any"))],
)
async def create_bug(
    body: BugCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugRead:
    """Create a new bug report.

    Behaviour:

    - ``bug_type`` defaults to ``"production"`` when the caller passes
      ``feature_id`` (Feature-linked = post-release). Otherwise it
      derives from the linked BUD's lifecycle status, or falls back to
      ``"testing"``. Callers may override explicitly via the body.
    - The AI linker auto-fills ``bud_id`` or ``feature_id`` (depending
      on ``bug_type``) when the caller left both blank. See
      :mod:`app.services.bug_linker` for the dispatch rules.
    - SP attribution is NOT applied at bug creation. QA / developer SP is
      settled at outcome time: per-complexity bug-threshold rules fire at
      BUD close (:mod:`app.services.sp_qa` / :mod:`app.services.dev_quality_sp`),
      and the production-bug-closed reward / bug-rejected penalty fire on the
      bug status transition (:func:`app.services.sp_qa.award_qa_sp_on_bug_status`).
    """
    bud_uuid = uuid.UUID(body.bud_id) if body.bud_id else None
    feature_uuid = uuid.UUID(body.feature_id) if body.feature_id else None

    bug_type = await _decide_bug_type(
        db, current_user.org_id, body.bug_type, bud_uuid, feature_uuid
    )

    bug_repo = BugRepository(db, org_id=current_user.org_id)
    bug = Bug(
        org_id=current_user.org_id,
        bug_number=await bug_repo.next_bug_number(),
        title=body.title,
        description=body.description,
        severity=body.severity,
        module=body.module,
        bud_id=bud_uuid,
        feature_id=feature_uuid,
        bug_type=bug_type,
        reporter_id=current_user.id,
    )

    bug = await bug_repo.create(bug)

    # Embed + auto-link inline so the response includes the resolved link.
    # ~100 ms embed + 1 hnsw / pgvector lookup. The linker dispatches by
    # ``bug.bug_type``; see app/services/bug_linker.py.
    if bud_uuid is None and feature_uuid is None:
        try:
            await embed_and_link_bug(db, current_user.org_id, bug)
            # Always flush + refresh — the linker mutates bug.embedding
            # (and possibly bug.bud_id / bug.feature_id / bug.bug_type),
            # which expires other ORM attributes. Without refresh,
            # accessing bug.updated_at in _bug_to_read trips MissingGreenlet.
            await db.flush()
            await db.refresh(bug)
        except Exception:
            logger.warning(
                "bug_embed_link_failed_inline",
                bug_id=str(bug.id),
                exc_info=True,
            )
    else:
        # One of the two links was provided manually — generate the
        # embedding in the background so future similarity searches work,
        # but don't block the response on it.
        _schedule_embedding(bug.id, current_user.org_id)

    # If the bug ended up against a BUD in testing, check whether the
    # open-bug count now exceeds the org's rejection threshold; that
    # path can auto-reject the BUD back to development.
    if bug.bud_id is not None:
        try:
            bud_repo = BUDRepository(db, org_id=current_user.org_id)
            linked_bud = await bud_repo.get_by_id(bug.bud_id)
            if linked_bud is not None:
                await check_bug_threshold(db, current_user.org_id, linked_bud)
                await db.flush()
        except Exception:
            logger.warning(
                "bug_threshold_check_failed",
                bug_id=str(bug.id),
                exc_info=True,
            )

    return await bug_to_read(db, bug, current_user.org_id)


@router.get(
    "",
    response_model=BugListResponse,
    response_model_by_alias=True,
    # Dual-gate for the migration window — see POST /bugs notes.
    dependencies=[Depends(require_permissions("bugs:view", "buds:view", mode="any"))],
)
async def list_bugs(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    status_filter: str | None = Query(None, alias="status"),
    severity: str | None = None,
    bud_id: str | None = Query(None, alias="budId"),
    feature_id: str | None = Query(None, alias="featureId"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100, alias="pageSize"),
) -> BugListResponse:
    """List bugs with optional filters and pagination."""
    bug_repo = BugRepository(db, org_id=current_user.org_id)
    items, total = await bug_repo.list_filtered(
        status=status_filter,
        severity=severity,
        bud_id=uuid.UUID(bud_id) if bud_id else None,
        feature_id=uuid.UUID(feature_id) if feature_id else None,
        page=page,
        page_size=page_size,
    )
    list_items = await bugs_to_list_items(db, items, current_user.org_id)
    return BugListResponse(items=list_items, total=total, page=page, page_size=page_size)


@router.get(
    "/board",
    response_model=BugBoardResponse,
    response_model_by_alias=True,
    # Dual-gate for the migration window — see POST /bugs notes.
    dependencies=[Depends(require_permissions("bugs:view", "buds:view", mode="any"))],
)
async def list_bug_board(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    bug_type: str | None = Query(None, alias="bugType"),
    severity: str | None = None,
    feature_id: str | None = Query(None, alias="featureId"),
    assignee_id: str | None = Query(None, alias="assigneeId"),
) -> BugBoardResponse:
    """Bugs grouped by status for the Kanban board.

    Defaults to ``bug_type='production'`` so the /bugs page shows only
    Feature-linked bugs (BUDBugsPanel still shows testing bugs against
    the BUD). Callers may pass ``bugType=testing`` for the QA-side
    board, or ``bugType=all`` to request the union.
    """
    bug_repo = BugRepository(db, org_id=current_user.org_id)
    resolved_bug_type: str | None
    if bug_type is None:
        resolved_bug_type = BugType.PRODUCTION.value
    elif bug_type == "all":
        resolved_bug_type = None
    else:
        resolved_bug_type = bug_type
    items = await bug_repo.list_board(
        bug_type=resolved_bug_type,
        severity=severity,
        feature_id=uuid.UUID(feature_id) if feature_id else None,
        assignee_id=uuid.UUID(assignee_id) if assignee_id else None,
    )
    list_items = await bugs_to_list_items(db, items, current_user.org_id)
    columns: dict[str, list[BugListItem]] = {s.value: [] for s in BugStatus}
    for it in list_items:
        columns.setdefault(it.status, []).append(it)
    return BugBoardResponse(columns=columns, total=len(list_items))


@router.get(
    "/{bug_id}",
    response_model=BugRead,
    response_model_by_alias=True,
    # Dual-gate for the migration window — see POST /bugs notes.
    dependencies=[Depends(require_permissions("bugs:view", "buds:view", mode="any"))],
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
    return await bug_to_read(db, bug, current_user.org_id)


@router.patch(
    "/{bug_id}",
    response_model=BugRead,
    response_model_by_alias=True,
    # Dual-gate for the migration window — see POST /bugs notes.
    dependencies=[Depends(require_permissions("bugs:edit", "buds:edit", mode="any"))],
)
async def update_bug(
    bug_id: uuid.UUID,
    body: BugUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugRead:
    """Update a bug (status, assignee, severity, link, etc.)."""
    bug_repo = BugRepository(db, org_id=current_user.org_id)
    bug = await bug_repo.get_by_id(bug_id)
    if not bug:
        raise HTTPException(status_code=404, detail="Bug not found")

    update = body.model_dump(exclude_unset=True, by_alias=False)

    # Reassignment is a narrower privilege than general bug edit. Devs /
    # tech leads can resolve a bug but only manager / pm / admin can
    # change who owns it; keep that boundary even though the endpoint's
    # outer gate accepts the wider ``bugs:edit``.
    if "assignee_id" in update:
        perms = await get_user_permissions(current_user, db)
        if "bugs:assign" not in perms:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Reassigning bugs requires bugs:assign.",
            )

    if "bud_id" in update:
        update["bud_id"] = uuid.UUID(update["bud_id"]) if update["bud_id"] else None
        if update["bud_id"] is not None:
            bud_check = BUDRepository(db, org_id=current_user.org_id)
            if not await bud_check.get_by_id(update["bud_id"]):
                raise HTTPException(status_code=404, detail="BUD not found")
    if "feature_id" in update:
        update["feature_id"] = uuid.UUID(update["feature_id"]) if update["feature_id"] else None
        if update["feature_id"] is not None:
            feature_check = FeatureRepository(db, org_id=current_user.org_id)
            if not await feature_check.get_by_id(update["feature_id"]):
                raise HTTPException(status_code=404, detail="Feature not found")
    if "assignee_id" in update:
        update["assignee_id"] = uuid.UUID(update["assignee_id"]) if update["assignee_id"] else None

    # Stamp ``resolved_at`` on first transition to resolved / closed.
    if (
        "status" in update
        and update["status"] in (BugStatus.RESOLVED, BugStatus.CLOSED)
        and not bug.resolved_at
    ):
        update["resolved_at"] = datetime.now(UTC)

    # Stamp ``rejected_at`` on first transition to rejected. This marks the
    # bug as never-valid (vs ``closed`` = fixed) and is the signal the QA
    # false-positive SP penalty keys off.
    if "status" in update and update["status"] == BugStatus.REJECTED and not bug.rejected_at:
        update["rejected_at"] = datetime.now(UTC)

    for field, value in update.items():
        setattr(bug, field, value)
    await db.flush()
    await db.refresh(bug)

    # Settle QA SP on a status change: reward a confirmed (closed) production
    # bug, penalise a rejected one. Best-effort + deduped inside the service.
    if "status" in update:
        await award_qa_sp_on_bug_status(db, bug, BugStatus(bug.status))

    return await bug_to_read(db, bug, current_user.org_id)


# ── Helpers ──────────────────────────────────────────────────────────


_background_tasks: set[asyncio.Task[None]] = set()


async def _decide_bug_type(
    db: AsyncSession,
    org_id: uuid.UUID,
    explicit: str | None,
    bud_uuid: uuid.UUID | None,
    feature_uuid: uuid.UUID | None,
) -> str:
    """Resolve the ``bug_type`` to persist.

    Precedence: explicit > Feature-linked (always production) > linked
    BUD's lifecycle status > default 'testing'. The auto-link path may
    later override this when the linker matches a Feature.
    """
    if explicit:
        return explicit
    if feature_uuid is not None:
        return BugType.PRODUCTION.value
    if bud_uuid is not None:
        bud_repo = BUDRepository(db, org_id=org_id)
        linked = await bud_repo.get_by_id(bud_uuid)
        if linked and linked.status in ("uat", "prod", "closed"):
            return BugType.PRODUCTION.value
    return BugType.TESTING.value


def _schedule_embedding(bug_id: uuid.UUID, org_id: uuid.UUID) -> None:
    """Fire-and-forget: generate the embedding only (link already set)."""
    task = asyncio.create_task(
        _bg_embed(bug_id, org_id),
        name=f"bug_embed_{bug_id}",
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _bg_embed(bug_id: uuid.UUID, org_id: uuid.UUID) -> None:
    """Background: generate embedding for a bug (no auto-link)."""
    try:
        async with AsyncSessionLocal() as db:
            bug_repo = BugRepository(db, org_id=org_id)
            bug = await bug_repo.get_by_id(bug_id)
            if not bug:
                return
            text = bug.title
            if bug.description:
                text = f"{text} {bug.description}"
            bug.embedding = await embedding_service.embed(text)
            await db.commit()
    except Exception:
        logger.warning("bug_embed_failed", bug_id=str(bug_id), exc_info=True)
