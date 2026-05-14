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

"""Helpers for originating-agent CLI session bookkeeping.

Each BUD section is authored by an AI agent that owns a Claude CLI
session id. Subsequent user chats on that section ``--resume`` the same
session so reasoning context + prompt cache are preserved across turns.

These helpers are the single place where originating agents (PRD,
tech-arch, test-planner, designer) mint and persist their session ids.
The repository — :class:`BUDSectionSessionRepository` — owns SQL; this
module owns the cross-handler wiring so the bookkeeping doesn't get
copy-pasted across every job module.
"""

import uuid
from dataclasses import dataclass

import structlog

from app.database import AsyncSessionLocal
from app.repositories.bud_section_session import BUDSectionSessionRepository
from app.schemas.bud_constants import SECTION_SESSION_MESSAGE_CAP

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ResolvedSession:
    """Outcome of resolving the CLI session for a chat turn.

    ``is_resume`` is ``True`` when the caller should pass ``--resume``;
    ``False`` when it should pass ``--session-id`` (first turn or
    rotation). ``rotated`` is ``True`` when the row's session id just
    changed (caller surfaces this to the UI so it can show a
    "Starting fresh thread" toast).
    """

    session_id: uuid.UUID
    is_resume: bool
    rotated: bool


def mint_session_id() -> uuid.UUID:
    """Mint a fresh CLI session id for an originating agent run.

    Wrapper around ``uuid.uuid4()`` so the call site reads clearly and
    so tests can monkeypatch the source of randomness if needed.
    """
    return uuid.uuid4()


async def record_originating_session(
    *,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    section: str,
    session_id: uuid.UUID,
    design_id: uuid.UUID | None = None,
) -> None:
    """Persist (or refresh) the originating-agent session row.

    Opens its own ``AsyncSessionLocal`` so the call is independent of
    whatever transaction the caller is holding — this row needs to land
    even if the surrounding job session commits later. Soft-fails on
    DB errors so a transient persistence hiccup does not fail the
    agent run (the chat-side flow will simply mint a new session on
    first user message instead of resuming).
    """
    try:
        async with AsyncSessionLocal() as db:
            repo = BUDSectionSessionRepository(db, org_id=org_id)
            await repo.upsert(bud_id, section, session_id, design_id=design_id)
            await db.commit()
    except Exception:
        logger.warning(
            "section_session_upsert_failed",
            bud_id=str(bud_id),
            section=section,
            design_id=str(design_id) if design_id else None,
            exc_info=True,
        )


async def resolve_chat_session(
    *,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    section: str,
    design_id: uuid.UUID | None = None,
) -> ResolvedSession:
    """Resolve the CLI session id for a chat turn against ``(bud, section)``.

    Rules:

    * No existing row → mint a fresh id, ``is_resume=False`` (claim).
    * Existing row with ``message_count >= SECTION_SESSION_MESSAGE_CAP``
      → rotate to a new id, ``is_resume=False``, ``rotated=True``.
    * Otherwise → reuse the row's id, ``is_resume=True``.

    The repository commits its own write inside an ``AsyncSessionLocal``
    so the caller's transaction is independent of the bookkeeping.
    """
    async with AsyncSessionLocal() as db:
        repo = BUDSectionSessionRepository(db, org_id=org_id)
        row = await repo.get_active(bud_id, section, design_id=design_id)
        if row is None:
            new_id = uuid.uuid4()
            await repo.upsert(bud_id, section, new_id, design_id=design_id)
            await db.commit()
            return ResolvedSession(session_id=new_id, is_resume=False, rotated=False)
        if row.message_count >= SECTION_SESSION_MESSAGE_CAP:
            new_id = uuid.uuid4()
            rotated = await repo.rotate(row.id, new_id)
            await db.commit()
            if rotated is None:
                # Row vanished between fetch and rotate (BUD cascade).
                return ResolvedSession(session_id=new_id, is_resume=False, rotated=True)
            return ResolvedSession(session_id=rotated.session_id, is_resume=False, rotated=True)
        return ResolvedSession(session_id=row.session_id, is_resume=True, rotated=False)


async def bump_chat_session_count(
    *,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    section: str,
    design_id: uuid.UUID | None = None,
) -> None:
    """Increment ``message_count`` on the active session row.

    No-op if the row has been deleted between resolve and bump (the
    BUD cascade may have run). Soft-fails on DB errors — a missed
    increment only means the next turn may not rotate exactly at the
    cap, which is well within the rotation policy's tolerance.
    """
    try:
        async with AsyncSessionLocal() as db:
            repo = BUDSectionSessionRepository(db, org_id=org_id)
            row = await repo.get_active(bud_id, section, design_id=design_id)
            if row is None:
                return
            await repo.increment_message_count(row.id)
            await db.commit()
    except Exception:
        logger.warning(
            "section_session_bump_failed",
            bud_id=str(bud_id),
            section=section,
            design_id=str(design_id) if design_id else None,
            exc_info=True,
        )
