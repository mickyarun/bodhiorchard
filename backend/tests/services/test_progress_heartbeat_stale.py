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

"""The "still generating" heartbeat never overwrites a later status.

The heartbeat is a timer armed by the last tool call. It must not replace a
message the handler set afterwards, nor the terminal message of a job that
has already finished.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from app.schemas.jobs import JobState
from app.services import event_bus, job_queue, job_utils

DELAY = 0.02


async def _noop(job_id: str, payload: dict[str, Any]) -> None:
    """Registered so jobs can be created; no worker runs it."""


@pytest.fixture
def frames(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """An isolated job store, a short heartbeat, and every published frame."""
    published: list[tuple[str, dict[str, Any]]] = []

    async def record(topic: str, data: dict[str, Any]) -> None:
        published.append((topic, data))

    monkeypatch.setattr(job_queue, "_registry", {})
    monkeypatch.setattr(job_queue, "_job_store", {})
    monkeypatch.setattr(event_bus, "_transports", [record])
    monkeypatch.setattr(job_utils, "_HEARTBEAT_DELAY_SECONDS", DELAY)
    job_queue.register_job_type("heartbeat_probe", _noop)
    return published


def _running_job() -> str:
    job_id = job_queue.create_job("heartbeat_probe", payload={}).job_id
    job_queue.update_job(job_id, state=JobState.RUNNING, status_message="Starting...")
    return job_id


def _message(job_id: str) -> str:
    job = job_queue.get_job(job_id)
    assert job is not None
    return job.status_message


async def test_quiet_run_still_gets_the_generating_message(
    frames: list[tuple[str, dict[str, Any]]],
) -> None:
    job_id = _running_job()
    job_utils.make_progress_callback(job_id, generating_message="Drawing...")("Read", {})
    await asyncio.sleep(DELAY * 5)
    assert _message(job_id) == "Drawing..."


async def test_finished_job_keeps_its_terminal_message(
    frames: list[tuple[str, dict[str, Any]]],
) -> None:
    job_id = _running_job()
    job_utils.make_progress_callback(job_id, generating_message="Drawing...")("Read", {})
    job_queue.update_job(job_id, state=JobState.COMPLETED, status_message="Done")
    await asyncio.sleep(DELAY * 5)
    await asyncio.sleep(0)

    assert _message(job_id) == "Done"
    assert [f["statusMessage"] for _, f in frames][-1] == "Done"


async def test_later_handler_message_is_not_replaced(
    frames: list[tuple[str, dict[str, Any]]],
) -> None:
    job_id = _running_job()
    job_utils.make_progress_callback(job_id, generating_message="Drawing...")("Read", {})
    job_queue.update_job(job_id, status_message="Saving results...")
    await asyncio.sleep(DELAY * 5)

    assert _message(job_id) == "Saving results..."
