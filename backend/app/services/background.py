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

"""Fire-and-forget background work started after a request commits.

Keeps a reference to each task until it finishes so the event loop can't
garbage-collect it mid-flight. Use for best-effort side effects (Slack
messages) whose failure must not fail the request.
"""

import asyncio
from collections.abc import Coroutine
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

_tasks: set[asyncio.Task[None]] = set()


def spawn(job: Coroutine[Any, Any, None]) -> None:
    """Run ``job`` in the background; a failure is logged, never raised."""
    task = asyncio.create_task(job, name=job.__qualname__)
    _tasks.add(task)
    task.add_done_callback(_finished)


def _finished(task: asyncio.Task[None]) -> None:
    _tasks.discard(task)
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        # Otherwise only "Task exception was never retrieved", with no name.
        logger.error("background_job_failed", job=task.get_name(), exc_info=exc)
