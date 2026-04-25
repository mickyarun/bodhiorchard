# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Session lifecycle helpers — the only sanctioned way phases acquire DB state.

Two primitives, both small:

- ``with_session(org_id)`` opens an ``AsyncSessionLocal`` scoped to a
  single logical operation. Commits on clean exit, rolls back on any
  exception, then re-raises so the caller still sees the failure.

- ``gather_repos(coros, max_concurrent=…)`` wraps ``asyncio.gather``
  with a semaphore so we never run more parallel coroutines than the
  asyncpg pool can sustain. The legacy ``phase_b2_synthesis`` ran 20
  concurrent ``_synthesize_repo`` tasks; with 10 pool slots and 2-3
  connections per task, we'd blow past the pool and trigger
  ``InvalidRequestError: another operation is in progress`` even with
  per-task sessions. Capping at 4 keeps headroom.

Phases use these directly. The orchestrator never passes a session
across function boundaries; sessions belong to the phase that opens
them and die when its ``async with`` exits.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator, Awaitable, Iterable
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal

# Default concurrency cap for repo-fanout phases. Picked to leave the
# asyncpg pool (~10 slots in dev, configurable in prod) with headroom
# for the rest of the request mix. Bump only after confirming the pool
# size is configured upward in lockstep.
DEFAULT_REPO_CONCURRENCY = 4


@asynccontextmanager
async def with_session(_org_id: uuid.UUID) -> AsyncIterator[AsyncSession]:
    """Yield a fresh ``AsyncSession`` that commits on success, rolls back on raise.

    ``_org_id`` is accepted (and required by callers) so every checkpoint
    or repository instantiated against this session has the tenant scope
    visible at the call site — even though the function body does not
    yet route on it. The leading underscore signals "deliberately unused
    inside the helper"; future per-tenant connection routing or audit
    tagging plugs in here without touching every call site.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def gather_repos[T](
    coros: Iterable[Awaitable[T]],
    *,
    max_concurrent: int = DEFAULT_REPO_CONCURRENCY,
) -> list[T | BaseException]:
    """Bounded ``asyncio.gather`` for repo-fanout work.

    Wraps each coroutine in a semaphore acquisition so at most
    ``max_concurrent`` of them are in flight at once. Behaviour
    otherwise matches ``asyncio.gather(..., return_exceptions=True)`` —
    every coroutine runs, exceptions surface in the result list rather
    than raising eagerly, and order is preserved.

    Use this for any phase that fans out across repos. Sequential code
    paths should call ``asyncio.gather`` directly — the bounding adds
    setup cost not justified for two or three coroutines.
    """
    if max_concurrent < 1:
        raise ValueError(f"max_concurrent must be >= 1, got {max_concurrent}")
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _bounded(coro: Awaitable[T]) -> T:
        async with semaphore:
            return await coro

    return await asyncio.gather(
        *(_bounded(c) for c in coros),
        return_exceptions=True,
    )
