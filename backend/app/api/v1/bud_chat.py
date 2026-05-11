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

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, require_permissions
from app.models.bud import BUDDesignStatus
from app.models.user import User
from app.repositories.bud import BUDChatMessageRepository, BUDDesignRepository, BUDRepository
from app.schemas.bud import SECTION_PATTERN, ChatMessageRead
from app.schemas.jobs import ChatJobPayload, JobCreatedResponse
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
) -> list[dict]:
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
    response_model=JobCreatedResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(require_permissions("buds:edit"))],
)
async def chat_bud(
    bud_id: uuid.UUID,
    body: BUDChatRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> JobCreatedResponse:
    """Submit a BUD chat request for async AI processing."""
    bud_repo = BUDRepository(db, org_id=current_user.org_id)
    bud = await bud_repo.get_by_id(bud_id)
    if bud is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BUD not found")

    # Resolve current content — for design, use bud_designs table
    design_repo_id: str | None = None
    if body.section == "design":
        current_content = ""
        if body.design_id:
            design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
            design = await design_repo.get_by_id(body.design_id)
            if design:
                design_repo_id = str(design.repo_id) if design.repo_id else None
                if design.design_html:
                    current_content = design.design_html
        if not current_content:
            design_repo = BUDDesignRepository(db, org_id=current_user.org_id)
            all_designs = await design_repo.list_for_bud(bud_id)
            for d in all_designs:
                if d.status == BUDDesignStatus.READY and d.design_html:
                    current_content = d.design_html
                    if not design_repo_id and d.repo_id:
                        design_repo_id = str(d.repo_id)
                    break
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
        session_id=body.session_id,
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
        session_id=str(body.session_id) if body.session_id else None,
        images=body.images,
    )

    job = create_job(JOB_BUD_CHAT, payload=payload.model_dump(), user_id=str(current_user.id))
    return JobCreatedResponse(job_id=job.job_id)
