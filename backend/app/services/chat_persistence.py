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

    Todo regeneration and re-estimation are intentionally NOT triggered
    here. The tech spec stays mutable through chat / manual / agent
    re-runs during planning; todos crystallize from the *approved* plan
    at the DEVELOPMENT-phase transition — see
    ``services/bud_development.on_bud_development_started``.
    """
    async with AsyncSessionLocal() as db:
        bud_repo = BUDRepository(db, org_id=uuid_mod.UUID(org_id))
        bud = await bud_repo.get_by_id(uuid_mod.UUID(bud_id))
        if bud is not None:
            setattr(bud, section, content)
            await db.commit()
            logger.info("chat_content_persisted", bud_id=bud_id, section=section)
