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

"""Force two transactions into the worst write interleaving, without sleeps.

The first writer's change stays uncommitted while the second writer runs in
its own transaction. The second writer's backend is watched in
``pg_stat_activity`` until it is waiting on a lock (or has finished without
ever waiting), then the first commits and the second is awaited. A
select-then-insert upsert fails this every time: the second writer sees no
committed row, inserts, and either duplicates the row or hits a unique
violation once the first commits.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

Write = Callable[[AsyncSession], Awaitable[object]]

_TIMEOUT_S = 10.0


async def _waits_on_lock(
    factory: async_sessionmaker[AsyncSession], pid: int, writer: asyncio.Task[None]
) -> bool:
    """True once backend ``pid`` waits on a lock; False if ``writer`` ends first."""
    async with asyncio.timeout(_TIMEOUT_S), factory() as db:
        while not writer.done():
            wait_type = (
                await db.execute(
                    text("SELECT wait_event_type FROM pg_stat_activity WHERE pid = :pid"),
                    {"pid": pid},
                )
            ).scalar_one_or_none()
            if wait_type == "Lock":
                return True
            await asyncio.sleep(0.01)
    return False


async def race_against_uncommitted(
    factory: async_sessionmaker[AsyncSession], first: Write, second: Write
) -> bool:
    """Run ``second`` while ``first``'s write is uncommitted; commit both.

    Returns whether ``second`` was waiting on a lock before ``first``
    committed. Errors from either writer propagate.
    """
    pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()

    async def run_second() -> None:
        async with factory() as db:
            pid.set_result((await db.execute(text("SELECT pg_backend_pid()"))).scalar_one())
            await second(db)
            await db.commit()

    async with factory() as db_first:
        await first(db_first)
        writer = asyncio.create_task(run_second())
        try:
            started: set[asyncio.Future[Any]] = {pid, writer}
            await asyncio.wait(started, timeout=_TIMEOUT_S, return_when=asyncio.FIRST_COMPLETED)
            if not pid.done():
                if writer.done():
                    await writer  # died before it started: re-raise why
                raise TimeoutError("second writer never reached the database")
            try:
                blocked = await _waits_on_lock(factory, pid.result(), writer)
            except TimeoutError as exc:
                raise TimeoutError("second writer neither waited on a lock nor finished") from exc
            await db_first.commit()
            await writer
        finally:
            # On failure, stop the writer without raising its result: the
            # original error is the one worth reporting, and a cancel aimed
            # at this task must still propagate.
            if not writer.done():
                writer.cancel()
                await asyncio.wait({writer})
            if not writer.cancelled():
                writer.exception()  # mark any writer error as retrieved
    return blocked
