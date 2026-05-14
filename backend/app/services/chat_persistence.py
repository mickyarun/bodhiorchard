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
from app.services.event_bus import publish
from app.services.tech_planner_patch import apply_tech_spec_edit

logger = structlog.get_logger(__name__)

_TECH_SPEC_SECTION = "tech_spec_md"


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

    For ``tech_spec_md`` edits on a BUD already in DEVELOPMENT, the
    Implementation TODO section is refreshed (LLM patch on body changes,
    no-op when the diff is purely inside the section) and BUDTodo rows
    are re-derived. The reconciler preserves in-flight developer work
    via :func:`sync_todos_for_bud`. Pre-DEVELOPMENT spec edits write
    through unchanged — TODOs crystallize at the dev-phase transition.
    """
    org_uuid = uuid_mod.UUID(org_id)
    bud_uuid = uuid_mod.UUID(bud_id)
    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=org_uuid)
        # Row-lock the BUD before mutating section content so a second
        # concurrent chat on the same section serializes at the DB row
        # level instead of racing on a read→setattr→commit window. The
        # lock releases on commit below.
        bud = await bud_repo.get_by_id_for_update(bud_uuid)
        if bud is None:
            return

        old_value = getattr(bud, section, None)
        setattr(bud, section, content)
        await db.commit()
        logger.info("chat_content_persisted", bud_id=bud_id, section=section)

        if section != _TECH_SPEC_SECTION:
            return

        # Second phase: refresh the Implementation TODO section + BUDTodo
        # rows. Failures here must NOT abandon the already-committed spec
        # edit — log + publish a banner event but let the chat job carry
        # on with its own follow-up writes (the user still sees their
        # edited spec; only the TODO refresh is missing).
        try:
            await apply_tech_spec_edit(
                bud=bud,
                old_spec=old_value,
                new_spec=content,
                db=db,
                org_id=org_uuid,
            )
            await db.commit()
        except Exception as exc:
            await db.rollback()
            logger.warning(
                "chat_tech_spec_todo_refresh_failed",
                bud_id=bud_id,
                error=str(exc),
            )
            publish(
                f"todo:{bud_id}",
                {"event": "generating_failed", "error": str(exc)},
            )
