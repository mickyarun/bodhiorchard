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

"""BUD chat endpoints: chat history and chat submission."""

import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.user import User
from app.repositories.bud import BUDChatMessageRepository, BUDDesignRepository, BUDRepository
from app.repositories.bud_section_session import BUDSectionSessionRepository
from app.schemas.bud import ChatMessageRead
from app.schemas.bud_constants import SECTION_PATTERN, SECTION_REQUIRED_STAGES
from app.schemas.jobs import ChatJobCreatedResponse, ChatJobPayload, JobState, JobStatusRead
from app.services.job_queue import (
    JOB_BUD_CHAT,
    create_job_with_id,
    get_job,
)

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get(
    "/chat-history",
    response_model=list[ChatMessageRead],
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_chat_history(
    bud_id: uuid.UUID,
    section: str = Query("requirements_md"),
    design_id: uuid.UUID | None = Query(None),
    session_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    """Load persisted chat messages for a BUD section (and optional design/session).

    When ``session_id`` is omitted, resolve the *active* session for the
    ``(bud, section[, design])`` thread from ``bud_section_sessions`` so the
    client sees the originating agent's history on first open. Without
    this, ``list_messages`` would filter ``session_id IS NULL`` and return
    nothing — every message now carries a real session id since the
    originating agent claims one before the first chat turn.
    """
    chat_repo = BUDChatMessageRepository(db, org_id=current_user.org_id)
    if session_id is None:
        section_session_repo = BUDSectionSessionRepository(db, org_id=current_user.org_id)
        active = await section_session_repo.get_active(bud_id, section, design_id)
        if active is not None:
            session_id = active.session_id
    messages = await chat_repo.list_messages(bud_id, section, design_id, session_id)
    return [
        {
            "id": m.id,
            "role": m.role,
            "message": m.message,
            "user_id": m.user_id,
            "session_id": m.session_id,
            "user_name": m.user.name if m.user else None,
            "created_at": m.created_at,
        }
        for m in messages
    ]


@router.get(
    "/chat/active-job",
    response_model=JobStatusRead | None,
    dependencies=[Depends(require_permissions("buds:view"))],
)
async def get_active_chat_job(
    bud_id: uuid.UUID,
    section: str = Query("requirements_md"),
    design_id: uuid.UUID | None = Query(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobStatusRead | None:
    """Return the in-flight chat job for this BUD section/design, if any.

    Used by the AI Editor chat panel on BUD-detail remount: it lets the
    frontend re-subscribe to a still-running chat job that was started
    in a previous mount of the same page, so the progress bar reappears
    instead of vanishing the moment the user navigates away and back.

    The lookup is anchored on the durable ``bud_section_sessions``
    pointer (single source of truth for "is a chat in progress here?"),
    then cross-checked against the in-memory ``_job_store`` for the
    live progress frame. If the pointer references a job that is no
    longer queued/running (worker crashed, backend restarted, terminal
    state already published), the pointer is lazily cleared so the
    next ``POST /chat`` isn't stuck at 409. The Phase-4 boot-time
    orphan sweep is the durable backstop for the same situation.

    Cross-org safety: ``BUDSectionSessionRepository`` is org-scoped on
    construction, so a request from a different org never sees another
    org's pointer.
    """
    session_repo = BUDSectionSessionRepository(db, org_id=current_user.org_id)
    pointer = await session_repo.get_active_job_pointer(bud_id, section, design_id)
    if pointer is None:
        return None

    live = get_job(pointer.job_id)
    if live is None or live.state not in (JobState.QUEUED, JobState.RUNNING):
        # Stale pointer: in-memory entry has been evicted or is already
        # terminal. Release the claim so the next chat send can proceed.
        await session_repo.clear_active_job(bud_id, section, design_id)
        await db.commit()
        return None
    return live


class BUDChatRequest(BaseModel):
    """Schema for a chat message about a BUD's content."""

    message: str = Field(..., min_length=1, max_length=5000)
    section: str = Field(
        "requirements_md",
        pattern=SECTION_PATTERN,
    )
    design_id: uuid.UUID | None = None
    session_id: uuid.UUID | None = None
    images: list[str] = Field(
        default_factory=list,
        max_length=3,
        description="Base64 data-URL images pasted from clipboard (max 3)",
    )


@router.post(
    "/chat",
    response_model=ChatJobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def chat_bud(
    bud_id: uuid.UUID,
    body: BUDChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChatJobCreatedResponse:
    """Submit a BUD chat request for async AI processing.

    The CLI ``session_id`` is owned by the backend now: the worker looks
    up (or rotates) the per-section row in ``bud_section_sessions`` and
    resumes the originating agent's thread. The client-provided
    ``body.session_id`` is accepted for backwards compatibility but is
    no longer authoritative — the worker echoes back the resolved id
    via the job result so the UI can keep its display continuity.

    Stage gate (409): if the BUD's current ``status`` is not in
    :data:`SECTION_REQUIRED_STAGES` for the requested section, the
    request is rejected with no DB write and no job enqueue. This
    prevents wireframe / spec edits from landing while the BUD is in
    the wrong lifecycle phase.
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    allowed_stages = SECTION_REQUIRED_STAGES.get(body.section)
    if allowed_stages is None:
        # Section is locked at every stage (e.g. ``test_plan_md``,
        # ``code_review``). Don't recommend a stage to move to — there
        # isn't one; chat is simply not available for this section.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Chat is not available for the '{body.section}' section.",
        )
    if bud.status not in allowed_stages:
        # Use the first allowed stage as the recommended target —
        # frontend renders this verbatim as the banner copy.
        target_stage = next(iter(sorted(allowed_stages)))
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Move BUD to '{target_stage}' before chatting in this section. "
                f"BUD is currently in '{bud.status}'."
            ),
        )

    # Backend owns session_id resolution. Look up the originating-agent
    # session row for this (bud, section[, design_id]); the worker will
    # rotate / mint as needed and the response carries the *resolved*
    # id back so the UI can keep its display continuity. Tagging the
    # user-message row with the same id keeps chat history filterable
    # by session_id across rotations.
    session_repo = BUDSectionSessionRepository(db, org_id=current_user.org_id)
    section_session = await session_repo.get_active(bud_id, body.section, design_id=body.design_id)
    fallback_session_id: uuid.UUID | None = (
        section_session.session_id if section_session is not None else body.session_id
    )

    # Atomic concurrency claim: pre-mint the job_id and stake it on the
    # ``bud_section_sessions`` row before anything else commits. The
    # claim is the source of truth for "is a chat already running on
    # this section?" — a second simultaneous POST loses the claim and
    # gets 409 ``chat_in_progress``, falling into watcher mode on the
    # frontend via the active-job endpoint. Persisting the user message
    # and enqueuing the job are gated on a successful claim so a 409
    # leaves no orphan rows in chat history.
    job_id = str(uuid.uuid4())
    claim = await session_repo.try_claim_active_job(
        bud_id,
        body.section,
        body.design_id,
        job_id,
        fallback_session_id=fallback_session_id,
    )
    if not claim.won:
        pointer = await session_repo.get_active_job_pointer(bud_id, body.section, body.design_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "error": "chat_in_progress",
                "message": "A chat is already in progress for this section.",
                "active_job_id": pointer.job_id if pointer else None,
                "started_at": pointer.started_at.isoformat() if pointer else None,
            },
        )
    # The repo ensures the row exists with a valid session_id on the
    # won path (preserved on update, freshly minted on insert), so the
    # assert narrows ``uuid.UUID | None`` to ``uuid.UUID`` for mypy.
    assert claim.session_id is not None, "won claim must carry a session_id"
    session_id: uuid.UUID = claim.session_id

    # Resolve repo scope for the design section so the worker can pass
    # ``repo_id`` to ``get_design_system`` / ``write_bud_design`` MCP calls.
    # The wireframe HTML itself is NOT loaded here — the agent fetches it
    # on demand via ``get_bud_designs``, so we never inline ~30KB of prior
    # HTML into the prompt or the job payload.
    design_repo_id: str | None = None
    if body.section == "design":
        current_content = ""
        if body.design_id:
            design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
            design = await design_repo.get_by_id(body.design_id)
            if design and design.repo_id:
                design_repo_id = str(design.repo_id)
    else:
        current_content = getattr(bud, body.section) or ""

    # Persist user message to chat history
    chat_repo = BUDChatMessageRepository(db, org_id=current_user.org_id)
    await chat_repo.add_message(
        bud_id=bud.id,
        section=body.section,
        role="user",
        message=body.message,
        design_id=body.design_id,
        user_id=current_user.id,
        session_id=session_id,
    )
    await db.flush()

    payload = ChatJobPayload(
        bud_id=str(bud.id),
        org_id=str(current_user.org_id),
        bud_number=bud.bud_number,
        section=body.section,
        current_content=current_content,
        title=bud.title,
        message=body.message,
        design_id=str(body.design_id) if body.design_id else None,
        repo_id=design_repo_id,
        user_id=str(current_user.id),
        session_id=str(session_id) if session_id else None,
        images=body.images,
    )

    # Enqueue against the id we already claimed. If enqueue fails (queue
    # full, shutdown, etc.) explicitly clear the claim. The surrounding
    # request transaction will also roll back on raise — which already
    # undoes the claim today — but the explicit clear keeps cleanup
    # correct if the transactional boundary ever shifts (e.g. a future
    # commit between claim and enqueue). No flush: rollback handles
    # persistence either way.
    try:
        job = create_job_with_id(
            job_id,
            JOB_BUD_CHAT,
            payload=payload.model_dump(),
            user_id=str(current_user.id),
        )
    except Exception:
        await session_repo.clear_active_job(bud_id, body.section, body.design_id)
        raise
    return ChatJobCreatedResponse(
        job_id=job.job_id,
        session_id=str(session_id),
    )
