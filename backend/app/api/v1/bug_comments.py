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

"""Bug comment-thread endpoints — post, list, edit, soft-delete.

Mounted at ``/api/v1/bugs/{bug_id}/comments``. All endpoints are
tenant-scoped (the bug ownership check rejects cross-org access
before touching the comment table).
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import (
    get_current_user,
    get_db,
    get_user_permissions,
    require_permissions,
)
from app.models.bug_comment import BugComment
from app.models.user import User
from app.repositories.bug import BugRepository
from app.repositories.bug_comment import BugCommentRepository
from app.repositories.user import UserRepository
from app.schemas.bug import (
    BugCommentCreate,
    BugCommentListResponse,
    BugCommentRead,
    BugCommentUpdate,
)

router = APIRouter(tags=["bug-comments"])

# Dual-gate per Step E: ``bugs:*`` is the new canonical family, the
# legacy ``buds:*`` fallbacks keep existing role tokens working while
# the seeder rolls out across orgs.
#
# Critical: the write fallback is ``buds:edit`` (not ``buds:view``).
# ``buds:view`` would let read-only roles (``viewer``) post / edit
# comments through the OR-gate — a privilege escalation. Anyone with
# ``buds:edit`` could already write to BUDs, so granting them comment
# rights during the migration window is consistent with prior trust.
#
# TODO(step-e-cleanup): drop the legacy fallback once all orgs have
# re-seeded. Search for this marker to find every dual-gate call site.
_VIEW_PERMS = ("bugs:view", "buds:view")
_COMMENT_PERMS = ("bugs:comment", "buds:edit")


@router.get(
    "/{bug_id}/comments",
    response_model=BugCommentListResponse,
    response_model_by_alias=True,
    dependencies=[Depends(require_permissions(*_VIEW_PERMS, mode="any"))],
)
async def list_bug_comments(
    bug_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugCommentListResponse:
    """All comments on a bug, oldest first.

    Soft-deleted comments are included so the UI can render
    ``[deleted]`` tombstones in thread position.
    """
    await _ensure_bug_in_org(db, current_user.org_id, bug_id)
    comments = await BugCommentRepository(db, org_id=current_user.org_id).list_for_bug(bug_id)
    items = await _comments_to_read(db, current_user.org_id, comments)
    return BugCommentListResponse(items=items, total=len(items))


@router.post(
    "/{bug_id}/comments",
    response_model=BugCommentRead,
    response_model_by_alias=True,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_permissions(*_COMMENT_PERMS, mode="any"))],
)
async def create_bug_comment(
    bug_id: uuid.UUID,
    body: BugCommentCreate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugCommentRead:
    """Post a comment to a bug's thread."""
    await _ensure_bug_in_org(db, current_user.org_id, bug_id)
    comment_repo = BugCommentRepository(db, org_id=current_user.org_id)
    comment = await comment_repo.create(
        BugComment(
            bug_id=bug_id,
            org_id=current_user.org_id,
            author_id=current_user.id,
            body=body.body,
        )
    )
    (single,) = await _comments_to_read(db, current_user.org_id, [comment])
    return single


@router.patch(
    "/{bug_id}/comments/{comment_id}",
    response_model=BugCommentRead,
    response_model_by_alias=True,
    dependencies=[Depends(require_permissions(*_COMMENT_PERMS, mode="any"))],
)
async def update_bug_comment(
    bug_id: uuid.UUID,
    comment_id: uuid.UUID,
    body: BugCommentUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugCommentRead:
    """Edit a comment's body. Author-only, with ``bugs:edit`` override."""
    await _ensure_bug_in_org(db, current_user.org_id, bug_id)
    comment_repo = BugCommentRepository(db, org_id=current_user.org_id)
    comment = await comment_repo.get_by_id(comment_id)
    if not comment or comment.bug_id != bug_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    await _ensure_can_modify(current_user, comment, db)
    if comment.deleted_at is not None:
        raise HTTPException(status_code=409, detail="Cannot edit a deleted comment")
    updated = await comment_repo.update_body(comment, body.body)
    (single,) = await _comments_to_read(db, current_user.org_id, [updated])
    return single


@router.delete(
    "/{bug_id}/comments/{comment_id}",
    response_model=BugCommentRead,
    response_model_by_alias=True,
    dependencies=[Depends(require_permissions(*_COMMENT_PERMS, mode="any"))],
)
async def delete_bug_comment(
    bug_id: uuid.UUID,
    comment_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> BugCommentRead:
    """Soft-delete a comment. Author-only, with ``bugs:edit`` override.

    Returns the tombstoned record so the UI can render the new state
    without an extra fetch.
    """
    await _ensure_bug_in_org(db, current_user.org_id, bug_id)
    comment_repo = BugCommentRepository(db, org_id=current_user.org_id)
    comment = await comment_repo.get_by_id(comment_id)
    if not comment or comment.bug_id != bug_id:
        raise HTTPException(status_code=404, detail="Comment not found")
    await _ensure_can_modify(current_user, comment, db)
    if comment.deleted_at is not None:
        # Idempotent — return current state without a second write.
        (single,) = await _comments_to_read(db, current_user.org_id, [comment])
        return single
    tombstoned = await comment_repo.soft_delete(comment)
    (single,) = await _comments_to_read(db, current_user.org_id, [tombstoned])
    return single


# ── Helpers ──────────────────────────────────────────────────────────


async def _ensure_bug_in_org(
    db: AsyncSession,
    org_id: uuid.UUID,
    bug_id: uuid.UUID,
) -> None:
    """404 if the bug doesn't exist or belongs to another org."""
    bug = await BugRepository(db, org_id=org_id).get_by_id(bug_id)
    if bug is None:
        raise HTTPException(status_code=404, detail="Bug not found")


async def _ensure_can_modify(
    current_user: User,
    comment: BugComment,
    db: AsyncSession,
) -> None:
    """Authors may always edit/delete their own comment.

    Moderators with the wider ``bugs:edit`` permission may modify
    anyone's comment in their org — the dual-gate also accepts the
    legacy ``buds:edit`` so role tokens minted before Step E rolled
    out keep working.
    """
    if comment.author_id == current_user.id:
        return
    perms = await get_user_permissions(current_user, db)
    if "bugs:edit" in perms or "buds:edit" in perms:
        return
    raise HTTPException(status_code=403, detail="Only the comment author may modify it")


async def _comments_to_read(
    db: AsyncSession,
    org_id: uuid.UUID,
    comments: list[BugComment],
) -> list[BugCommentRead]:
    """Batch-resolve author display names and serialise to BugCommentRead.

    Soft-deleted comments come through with ``body=""`` and the original
    ``author_id`` preserved — the UI uses ``deleted_at`` to render the
    tombstone in thread position without confusing comment ordering.
    """
    author_ids = {c.author_id for c in comments}
    names = await UserRepository(db, org_id=org_id).get_names_by_ids(author_ids)
    return [
        BugCommentRead(
            id=str(c.id),
            bug_id=str(c.bug_id),
            author_id=str(c.author_id),
            author_name=names.get(c.author_id),
            body="" if c.deleted_at is not None else c.body,
            edited_at=c.edited_at,
            deleted_at=c.deleted_at,
            created_at=c.created_at,
        )
        for c in comments
    ]
