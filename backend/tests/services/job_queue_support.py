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

"""A private, empty job queue for tests that drive real workers.

:func:`fresh_queue` swaps every piece of module state in
``app.services.job_queue`` for an empty copy and records what the queue
publishes and which notifications it sends, so a test sees only its own
jobs and nothing leaks to other tests.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

import pytest

from app.services import event_bus, job_queue, notification_service


@dataclass
class QueueSpy:
    """What the queue told the outside world while a test ran."""

    published: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    notified: list[dict[str, Any]] = field(default_factory=list)

    def states(self, job_id: str) -> list[str]:
        """The sequence of states pushed on ``job:<id>``."""
        return [data["state"] for topic, data in self.published if topic == f"job:{job_id}"]


def fresh_queue(monkeypatch: pytest.MonkeyPatch) -> QueueSpy:
    """Give the test an empty registry, store and worker list."""
    spy = QueueSpy()
    monkeypatch.setattr(job_queue, "_registry", {})
    monkeypatch.setattr(job_queue, "_job_store", {})
    monkeypatch.setattr(job_queue, "_running_tasks", {})
    monkeypatch.setattr(job_queue, "_workers", [])
    monkeypatch.setattr(job_queue, "_shutting_down", False)
    monkeypatch.setattr(event_bus, "publish", lambda t, d: spy.published.append((t, d)))
    monkeypatch.setattr(
        notification_service,
        "send_job_notification",
        lambda job, **kw: spy.notified.append({"state": job.state, **kw}),
    )
    return spy


async def idle(job_type: str) -> None:
    """Wait until every job enqueued for ``job_type`` has been processed."""
    _, _, queue = job_queue._registry[job_type]
    await asyncio.wait_for(queue.join(), timeout=5)
