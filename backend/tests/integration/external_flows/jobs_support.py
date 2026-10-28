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

"""Run the app's async jobs inline, and wait for its fire-and-forget tasks.

The routes under test answer ``202`` and hand the work to
``job_queue.create_job``; in production a worker picks it up. The tests
register the real handler on a private queue for one test (the module
registry is restored afterwards) and then run whatever was queued, in order,
on the test's own event loop, so the assertions see the finished work.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

import pytest

from app.schemas.jobs import JobState, JobStatusRead
from app.services import background, job_queue

JobHandler = Callable[[str, dict[str, Any]], Awaitable[None]]
_SETTLE_ROUNDS = 20


class InlineJobs:
    """Real job handlers on private queues, drained by the test."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._monkeypatch = monkeypatch
        self._queues: dict[str, asyncio.Queue[tuple[str, dict[str, Any]]]] = {}
        self.ran: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []

    def register(self, job_type: str, handler: JobHandler) -> None:
        """Accept ``job_type`` jobs for this test and run them with ``handler``."""
        queue: asyncio.Queue[tuple[str, dict[str, Any]]] = asyncio.Queue()
        self._queues[job_type] = queue
        self._monkeypatch.setitem(job_queue._registry, job_type, (handler, 1, queue))

    def queued(self, job_type: str) -> int:
        """How many ``job_type`` jobs are waiting."""
        return self._queues[job_type].qsize()

    async def run_all(self) -> list[str]:
        """Run every queued job (and any job those enqueue); return the job ids.

        Mirrors the queue's worker: the job is marked running first, and a
        handler that raises leaves the job failed with the error, the way
        the frontend would see it, rather than failing the test here.
        """
        done: list[str] = []
        while any(not q.empty() for q in self._queues.values()):
            for job_type, queue in self._queues.items():
                while not queue.empty():
                    job_id, payload = queue.get_nowait()
                    await self._run_one(job_type, job_id, payload)
                    done.append(job_id)
        return done

    async def _run_one(self, job_type: str, job_id: str, payload: dict[str, Any]) -> None:
        handler = job_queue._registry[job_type][0]
        job_queue.update_job(job_id, state=JobState.RUNNING, status_message="Starting...")
        try:
            await handler(job_id, payload)
        except Exception as exc:
            job_queue.update_job(
                job_id, state=JobState.FAILED, error=str(exc)[:500], status_message="Failed"
            )
            self.failed.append((job_type, job_id))
        self.ran.append((job_type, job_id))

    @staticmethod
    def status(job_id: str) -> JobStatusRead:
        """The job's final status from the in-memory job store."""
        found = job_queue.get_job(job_id)
        assert found is not None, f"unknown job {job_id}"
        return found


async def settle_background() -> None:
    """Wait for ``background.spawn`` tasks, including the ones they start."""
    for _ in range(_SETTLE_ROUNDS):
        pending = [task for task in background._tasks if not task.done()]
        if not pending:
            return
        await asyncio.gather(*pending, return_exceptions=True)
    raise AssertionError("background tasks kept spawning more work")
