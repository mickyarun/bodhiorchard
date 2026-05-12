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

"""Persistence layer for BUD chat — message storage, content updates, design saves.

Extracted from job_chat.py for modularity. Also imported by job_design.py.
"""

import uuid as uuid_mod

import structlog

from app.database import AsyncSessionLocal
from app.repositories.bud import BUDChatMessageRepository, BUDRepository
from app.services.bud_estimation import estimate_bud_dates
from app.services.todo_sync import sync_todos_from_tech_spec

logger = structlog.get_logger(__name__)


async def persist_chat_message(
    bud_id: str,
    org_id: str,
    section: str,
    role: str,
    message: str,
    design_id: str | None = None,
    user_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Save a chat message to the bud_chat_messages table."""
    async with AsyncSessionLocal() as db:
        chat_repo = BUDChatMessageRepository(db, org_id=uuid_mod.UUID(org_id))
        await chat_repo.add_message(
            bud_id=uuid_mod.UUID(bud_id),
            section=section,
            role=role,
            message=message,
            design_id=uuid_mod.UUID(design_id) if design_id else None,
            user_id=uuid_mod.UUID(user_id) if user_id else None,
            session_id=uuid_mod.UUID(session_id) if session_id else None,
        )
        await db.commit()


async def persist_chat_update(
    bud_id: str,
    org_id: str,
    section: str,
    content: str,
) -> None:
    """Write updated chat content to the BUD in the database.

    When ``section == "tech_spec_md"``, BUDTodo rows are re-synced from the
    new spec inside the same transaction — a sync failure rolls back the
    content change so spec and todos can never drift. Estimation re-runs
    after a successful commit and is non-fatal (mirrors the initial
    tech-arch agent path in ``agent_result_handlers``).
    """
    org_uuid = uuid_mod.UUID(org_id)
    bud_uuid = uuid_mod.UUID(bud_id)

    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=org_uuid)
        bud = await bud_repo.get_by_id(bud_uuid)
        if bud is None:
            return

        setattr(bud, section, content)

        if section == "tech_spec_md":
            try:
                await sync_todos_from_tech_spec(
                    db, org_uuid, bud.id, content, default_assignee_id=None
                )
            except Exception as exc:
                await db.rollback()
                logger.error(
                    "todo_sync_failed_after_chat_edit",
                    bud_id=bud_id,
                    error=str(exc),
                )
                raise RuntimeError(
                    "Failed to regenerate BUD todos from the updated tech "
                    f"architecture: {exc}. Tech spec change has been rolled back."
                ) from exc

        await db.commit()
        logger.info("chat_content_persisted", bud_id=bud_id, section=section)

        if section == "tech_spec_md":
            try:
                await db.refresh(bud)
                await estimate_bud_dates(db, org_uuid, bud, trigger="tech_arch_chat_edit")
            except Exception:
                logger.warning("estimation_failed_after_chat_tech_arch_edit", bud_id=bud_id)
