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

"""A job cancelled while it waits in the queue never runs.

``cancel_job`` flips a not-yet-started job straight to CANCELLED, but the
job stayed in the asyncio queue and the next free worker ran it anyway,
ending it COMPLETED (or FAILED) as if the cancel never happened. The
chat cancel service now signals queued jobs too, so it is covered here.
"""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import AsyncIterator
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.schemas.jobs import JobState
from app.services import event_bus, job_queue
from app.services.bud_chat_cancel import cancel_chat

JOB = "cancel_test_job"


class _BusyWorker:
    """One worker held on a first job, plus a record of what ran."""

    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.ran: list[str] = []

    async def handler(self, job_id: str, payload: dict[str, Any]) -> None:
        self.ran.append(payload["name"])
        if payload["name"] == "busy":
            self.started.set()
            await self.release.wait()
        job_queue.update_job(job_id, state=JobState.COMPLETED)

    async def start(self) -> None:
        """Start one worker and wait until it is inside the busy job."""
        job_queue.register_job_type(JOB, self.handler, worker_count=1)
        await job_queue.start_workers()
        job_queue.create_job(JOB, payload={"name": "busy"})
        await asyncio.wait_for(self.started.wait(), timeout=5)

    async def finish(self) -> None:
        """Let the busy job end and wait for the queue to empty."""
        self.release.set()
        _, _, queue = job_queue._registry[JOB]
        await asyncio.wait_for(queue.join(), timeout=5)


@pytest.fixture
async def worker(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[_BusyWorker]:
    """An empty registry and store, with event publishing silenced."""
    monkeypatch.setattr(job_queue, "_registry", {})
    monkeypatch.setattr(job_queue, "_job_store", {})
    monkeypatch.setattr(job_queue, "_running_tasks", {})
    monkeypatch.setattr(job_queue, "_workers", [])
    monkeypatch.setattr(job_queue, "_shutting_down", False)
    monkeypatch.setattr(event_bus, "publish", lambda topic, data: None)
    yield _BusyWorker()
    await job_queue.stop_workers()


async def test_job_cancelled_in_queue_is_skipped(worker: _BusyWorker) -> None:
    """With the only worker busy, a cancelled queued job is dropped, not run."""
    await worker.start()
    waiting = job_queue.create_job(JOB, payload={"name": "waiting"})
    after = job_queue.create_job(JOB, payload={"name": "after"})

    assert job_queue.cancel_job(waiting.job_id, reason="Cancelled by ana") is True
    await worker.finish()

    assert worker.ran == ["busy", "after"]
    cancelled = job_queue.get_job(waiting.job_id)
    assert cancelled is not None
    assert (cancelled.state, cancelled.error) == (JobState.CANCELLED, "Cancelled by ana")
    assert job_queue.get_job(after.job_id).state == JobState.COMPLETED  # type: ignore[union-attr]


async def test_chat_cancel_drops_a_queued_chat(worker: _BusyWorker) -> None:
    """Cancelling a chat that is still queued stops it and clears the pointer."""
    await worker.start()
    queued = job_queue.create_job(JOB, payload={"name": "chat"})
    repo = MagicMock(
        get_active_job_pointer=AsyncMock(return_value=MagicMock(job_id=queued.job_id)),
        clear_active_job=AsyncMock(),
    )
    db = MagicMock(commit=AsyncMock())
    bud_id = uuid.uuid4()

    with patch("app.services.bud_chat_cancel.BUDSectionSessionRepository", return_value=repo):
        out = await cancel_chat(
            db,
            org_id=uuid.uuid4(),
            bud_id=bud_id,
            section="requirements_md",
            design_id=None,
            reason="Cancelled by ana",
        )
    await worker.finish()

    assert out == queued.job_id
    assert worker.ran == ["busy"]
    assert job_queue.get_job(queued.job_id).state == JobState.CANCELLED  # type: ignore[union-attr]
    repo.clear_active_job.assert_awaited_once_with(bud_id, "requirements_md", None)
