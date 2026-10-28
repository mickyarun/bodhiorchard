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

"""The real job-queue workers, isolated to one test, plus a gate on agent spawns.

:class:`JobRuntime` swaps the queue's module state (registry, job store,
running tasks, workers) for empty containers, registers the real agent
handlers and starts real ``_worker`` loops, so a job goes through
``create_job`` → worker → handler → ``update_job`` exactly as in the app.
:class:`SpawnGate` holds a scripted ``claude`` spawn open until the test
releases it, which is how a test catches a job while it is running.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.schemas.jobs import JobState, JobStatusRead
from app.services import job_queue
from app.services.bud_agent_handler import handle_bud_agent_job
from app.services.job_agents import handle_triage_job
from app.services.job_design import handle_design_agent_job
from tests.fakes.claude_process import FakeProcess
from tests.fakes.claude_runner import FakeClaudeRunner

TERMINAL = frozenset({JobState.COMPLETED, JobState.FAILED, JobState.CANCELLED})


class JobRuntime:
    """Real workers for the BUD agent, design agent and triage job types."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(job_queue, "_registry", {})
        monkeypatch.setattr(job_queue, "_job_store", {})
        monkeypatch.setattr(job_queue, "_running_tasks", {})
        monkeypatch.setattr(job_queue, "_workers", [])
        monkeypatch.setattr(job_queue, "_shutting_down", False)

    async def start(self, *, workers: int = 1) -> None:
        """Register the agent handlers and spawn ``workers`` loops for each."""
        job_queue.register_job_type(
            job_queue.JOB_BUD_AGENT, handle_bud_agent_job, worker_count=workers
        )
        job_queue.register_job_type(
            job_queue.JOB_DESIGN_AGENT, handle_design_agent_job, worker_count=workers
        )
        job_queue.register_job_type(job_queue.JOB_TRIAGE, handle_triage_job, worker_count=1)
        await job_queue.start_workers()

    async def stop(self) -> None:
        """Cancel the worker loops (the queue's own shutdown path)."""
        await job_queue.stop_workers()

    async def wait(self, job_id: str, timeout: float = 5.0) -> JobStatusRead:
        """Poll until ``job_id`` is terminal and its handler has returned."""

        async def _poll() -> JobStatusRead:
            while True:
                job = job_queue.get_job(job_id)
                settled = not job_queue.is_job_running(job_id)
                if job is not None and job.state in TERMINAL and settled:
                    return job
                await asyncio.sleep(0.01)

        return await asyncio.wait_for(_poll(), timeout)

    async def wait_running(self, job_id: str, timeout: float = 5.0) -> None:
        """Poll until a handler task for ``job_id`` is in flight."""

        async def _poll() -> None:
            while not job_queue.is_job_running(job_id):
                await asyncio.sleep(0.01)

        await asyncio.wait_for(_poll(), timeout)


class SpawnGate:
    """Hold every scripted ``claude`` spawn until :meth:`release` is called."""

    def __init__(self, fake: FakeClaudeRunner, monkeypatch: pytest.MonkeyPatch) -> None:
        self.entered = asyncio.Event()
        self._open = asyncio.Event()
        real_spawn = fake.spawn

        async def gated(argv: list[str], kwargs: dict[str, Any]) -> FakeProcess:
            self.entered.set()
            await self._open.wait()
            return await real_spawn(argv, kwargs)

        monkeypatch.setattr(fake, "spawn", gated)

    def release(self) -> None:
        """Let held and future spawns through."""
        self._open.set()
