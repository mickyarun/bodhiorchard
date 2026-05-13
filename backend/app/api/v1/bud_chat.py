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
from app.schemas.bud import SECTION_PATTERN, ChatMessageRead
from app.schemas.jobs import ChatJobCreatedResponse, ChatJobPayload
from app.services.job_queue import JOB_BUD_CHAT, create_job

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
    """Load persisted chat messages for a BUD section (and optional design/session)."""
    chat_repo = BUDChatMessageRepository(db, org_id=current_user.org_id)
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

    For the ``design`` section, generates ``session_id`` server-side when
    the client omits one so the worker can pass it to ``--session-id`` /
    ``--resume`` and keep the Anthropic prompt cache warm across
    iterations of the same chat thread. The id is returned to the
    client so subsequent messages carry it forward.

    Other sections don't benefit from session affinity today (their
    workers don't pass ``--resume``), so we honour the client-provided
    id when present but don't manufacture one — avoiding a UUID churn
    that no consumer uses.
    """
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    if body.section == "design":
        session_id: uuid.UUID | None = body.session_id or uuid.uuid4()
    else:
        session_id = body.session_id

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

    job = create_job(JOB_BUD_CHAT, payload=payload.model_dump(), user_id=str(current_user.id))
    return ChatJobCreatedResponse(
        job_id=job.job_id,
        session_id=str(session_id) if session_id else "",
    )
