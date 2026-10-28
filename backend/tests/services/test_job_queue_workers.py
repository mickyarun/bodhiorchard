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

"""Real worker tasks running jobs: success, failure and cancellation.

Handlers coordinate with the test through ``asyncio.Event`` so nothing
waits on the clock. Each test gets an empty queue from
:func:`fresh_queue`.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from app.schemas.jobs import JobState
from app.services import job_queue
from tests.services.job_queue_support import QueueSpy, fresh_queue, idle

JOB = "test_job"


@pytest.fixture
async def spy(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[QueueSpy]:
    spy = fresh_queue(monkeypatch)
    yield spy
    await job_queue.stop_workers()


async def _start(handler: Any, workers: int = 1) -> None:
    job_queue.register_job_type(JOB, handler, worker_count=workers)
    await job_queue.start_workers()


async def test_handler_owns_completion_and_user_is_notified_once(spy: QueueSpy) -> None:
    """A finished job is COMPLETED with its result and notifies its owner."""

    async def handler(job_id: str, payload: dict[str, Any]) -> None:
        job_queue.update_job(job_id, state=JobState.COMPLETED, result={"n": payload["n"] * 2})

    await _start(handler)
    job = job_queue.create_job(JOB, payload={"n": 21, "org_id": "org-1"}, user_id="u-1")
    await idle(JOB)

    final = job_queue.get_job(job.job_id)
    assert final is not None
    assert (final.state, final.result) == (JobState.COMPLETED, {"n": 42})
    assert spy.states(job.job_id) == [JobState.RUNNING, JobState.COMPLETED]
    assert spy.notified == [
        {
            "state": JobState.COMPLETED,
            "user_id": "u-1",
            "org_id": "org-1",
            "payload": {"n": 21, "org_id": "org-1"},
        }
    ]


async def test_crashing_handler_fails_job_and_worker_keeps_going(spy: QueueSpy) -> None:
    """An exception marks that job FAILED (error capped) and the next job still runs."""

    async def handler(job_id: str, payload: dict[str, Any]) -> None:
        if payload["boom"]:
            raise RuntimeError("x" * 2000)
        job_queue.update_job(job_id, state=JobState.COMPLETED)

    await _start(handler)
    bad = job_queue.create_job(JOB, payload={"boom": True})
    good = job_queue.create_job(JOB, payload={"boom": False})
    await idle(JOB)

    failed = job_queue.get_job(bad.job_id)
    assert failed is not None
    assert (failed.state, failed.status_message, len(failed.error or "")) == (
        JobState.FAILED,
        "Failed",
        500,
    )
    assert spy.notified == []  # no user on these jobs
    assert job_queue.get_job(good.job_id).state == JobState.COMPLETED  # type: ignore[union-attr]


async def test_cancelling_a_running_job_interrupts_only_that_job(spy: QueueSpy) -> None:
    """cancel_job stops the live handler, records the reason and frees the worker."""
    started = asyncio.Event()
    cleaned_up = asyncio.Event()

    async def handler(job_id: str, payload: dict[str, Any]) -> None:
        if payload["block"]:
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned_up.set()
        job_queue.update_job(job_id, state=JobState.COMPLETED)

    await _start(handler)
    stuck = job_queue.create_job(JOB, payload={"block": True})
    after = job_queue.create_job(JOB, payload={"block": False})
    await asyncio.wait_for(started.wait(), timeout=5)

    assert job_queue.is_job_running(stuck.job_id)
    assert job_queue.cancel_job(stuck.job_id, reason="Cancelled by ana@acme.dev") is True
    await idle(JOB)

    cancelled = job_queue.get_job(stuck.job_id)
    assert cancelled is not None
    assert (cancelled.state, cancelled.error) == (JobState.CANCELLED, "Cancelled by ana@acme.dev")
    assert cleaned_up.is_set()
    assert spy.states(stuck.job_id) == [JobState.RUNNING, JobState.CANCELLED]
    assert not job_queue.is_job_running(stuck.job_id)
    assert job_queue.get_job(after.job_id).state == JobState.COMPLETED  # type: ignore[union-attr]


async def test_cancel_of_a_finished_job_is_a_no_op(spy: QueueSpy) -> None:
    """Terminal jobs keep their state and the call reports nothing cancelled."""

    async def handler(job_id: str, payload: dict[str, Any]) -> None:
        job_queue.update_job(job_id, state=JobState.COMPLETED, result="done")

    await _start(handler)
    job = job_queue.create_job(JOB, payload={})
    await idle(JOB)

    assert job_queue.cancel_job(job.job_id) is False
    assert job_queue.get_job(job.job_id).state == JobState.COMPLETED  # type: ignore[union-attr]
    assert job_queue.cancel_job("no-such-job") is False


async def test_parallel_workers_share_one_queue(spy: QueueSpy) -> None:
    """With two workers, two blocking jobs run at the same time."""
    both_running = asyncio.Barrier(3)

    async def handler(job_id: str, payload: dict[str, Any]) -> None:
        await both_running.wait()
        job_queue.update_job(job_id, state=JobState.COMPLETED)

    await _start(handler, workers=2)
    jobs = [job_queue.create_job(JOB, payload={}) for _ in range(2)]
    await asyncio.wait_for(both_running.wait(), timeout=5)
    await idle(JOB)

    assert {job_queue.get_job(j.job_id).state for j in jobs} == {JobState.COMPLETED}  # type: ignore[union-attr]


async def test_stop_workers_closes_the_queue(spy: QueueSpy) -> None:
    """After shutdown starts, new jobs are refused instead of silently queued."""

    async def handler(job_id: str, payload: dict[str, Any]) -> None:
        return None

    await _start(handler)
    await job_queue.stop_workers()

    with pytest.raises(RuntimeError, match="shutting down"):
        job_queue.create_job(JOB, payload={})
