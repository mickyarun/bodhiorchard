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

"""Fire-and-forget background work: a failure is logged by name, never raised."""

from __future__ import annotations

import asyncio

import pytest

from app.services import background
from tests.services.runner_internals.log_tap import LogTap


async def test_background_failure_is_logged_with_its_name_and_released(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``spawn`` never raises into the caller, logs the failed job and drops its reference."""
    tap = LogTap()
    tap.install(monkeypatch, background)

    async def post_to_slack() -> None:
        raise RuntimeError("slack down")

    async def fine() -> None:
        await asyncio.sleep(0)

    background.spawn(post_to_slack())
    background.spawn(fine())
    for _ in range(5):
        await asyncio.sleep(0)

    assert not [t for t in background._tasks if t.get_name().endswith(("post_to_slack", "fine"))]
    (failure,) = tap.records
    assert failure["event"] == "background_job_failed"
    assert failure["job"].endswith("post_to_slack")
    assert isinstance(failure["exc_info"], RuntimeError)
