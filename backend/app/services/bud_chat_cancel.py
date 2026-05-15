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

"""Cancellation of an in-flight BUD AI Editor chat job.

Modelled on :mod:`app.services.agent_task_cancel`. The chat flow is
simpler — no paired ``bud_agent_tasks`` row to flip, and no per-design
rollup — because the only durable state is the ``active_job_id``
pointer on ``bud_section_sessions``. The worker's ``finally`` hook in
:func:`app.services.job_chat.handle_chat_job` clears that pointer on
every terminal path, so this module only has to:

1. Resolve the active-job pointer for the ``(bud, section, design_id)``
   thread.
2. Signal the in-memory worker when the job is still alive.
3. Lazily clear the pointer on the stale-pointer path (post-restart or
   already-terminal job whose worker never wrote terminal state).

The API stays thin: validate inputs, delegate, translate
:class:`BUDChatCancelError` into an HTTP response.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.bud_section_session import BUDSectionSessionRepository
from app.services.job_queue import cancel_job as cancel_in_memory_job
from app.services.job_queue import is_job_running

logger = structlog.get_logger(__name__)


class BUDChatCancelError(Exception):
    """Raised when the cancel signal itself fails.

    Distinct from "no chat to cancel" (a normal ``None`` return) —
    this means we tried to stop a live Claude run and the job-queue
    refused. The API surfaces the message back to the user; no DB
    rows are touched so the spinner correctly keeps showing while
    the subprocess is still alive.
    """


async def cancel_chat(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    section: str,
    design_id: uuid.UUID | None,
    reason: str,
) -> str | None:
    """Cancel an in-flight chat job for the section, or report no-op.

    Args:
        db: Async session, committed before returning on the stale path.
        org_id: Caller's organization (scopes the repo).
        bud_id: The BUD whose chat is being cancelled.
        section: BUD section key (``requirements_md`` / ``design`` / …).
        design_id: Per-design thread id when the section is ``design``.
        reason: Human-readable reason for the cancel; recorded on the
            terminal WS frame so the UI can render it.

    Returns:
        The cancelled ``job_id`` when there was something to cancel,
        ``None`` when no chat was in flight (handler turns that into
        a 404).

    Raises:
        BUDChatCancelError: when signalling the live job blew up;
            callers should surface the message and write nothing.
    """
    repo = BUDSectionSessionRepository(db, org_id=org_id)
    pointer = await repo.get_active_job_pointer(bud_id, section, design_id)
    if pointer is None:
        return None

    job_id = pointer.job_id
    alive = is_job_running(job_id)

    if alive:
        try:
            cancel_in_memory_job(job_id, reason=reason)
        except Exception as exc:
            logger.warning(
                "bud_chat_cancel_signal_failed",
                bud_id=str(bud_id),
                section=section,
                job_id=job_id,
                error=str(exc),
            )
            raise BUDChatCancelError(str(exc)) from exc
        # Worker's terminal ``finally`` hook clears the DB pointer
        # after publishing the CANCELLED WS frame.
    else:
        # Stale pointer (post-restart or worker crashed before
        # publishing). Clear it directly so the next chat send can
        # claim the section immediately.
        await repo.clear_active_job(bud_id, section, design_id)
        await db.commit()

    logger.info(
        "bud_chat_cancel",
        org_id=str(org_id),
        bud_id=str(bud_id),
        section=section,
        design_id=str(design_id) if design_id else None,
        job_id=job_id,
        alive=alive,
    )

    return job_id
