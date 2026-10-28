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

"""Cancelling one repo's design and rolling the result up into the task.

A multi-repo design task stays running while any design is still
generating; once none is, it completes if one design is ready and fails
if none is.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.bud import BUDDesign, BUDDesignStatus
from app.services import agent_task_cancel
from app.services.agent_task_cancel import cancel_design
from tests.integration.agent_cancel_support import (
    AgentRun,
    Factory,
    add_design,
    design_status,
    running_task,
    task_state,
)

pytestmark = pytest.mark.integration

GENERATING = BUDDesignStatus.GENERATING


@pytest.fixture(autouse=True)
def _no_live_jobs(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(agent_task_cancel, "is_job_running", lambda job_id: False)


async def _cancel(factory: Factory, run: AgentRun, design_id: uuid.UUID) -> BUDDesignStatus:
    async with factory() as db:
        design = await db.get(BUDDesign, design_id)
        assert design is not None
        fresh = await cancel_design(db, org_id=run.org_id, design=design, reason="Stopped")
        return fresh.status


async def test_task_keeps_running_while_another_repo_generates(
    pg_session_factory: Factory,
) -> None:
    """Cancelling one of two generating designs leaves the task running."""
    run = await running_task(pg_session_factory)
    web = await add_design(pg_session_factory, run, GENERATING, job_id=run.job_id)
    app = await add_design(pg_session_factory, run, GENERATING, job_id=str(uuid.uuid4()))

    assert await _cancel(pg_session_factory, run, web) == BUDDesignStatus.FAILED

    assert await design_status(pg_session_factory, app) == GENERATING
    assert await task_state(pg_session_factory, run.task_id) == ("running", None)


async def test_task_completes_when_the_rest_are_ready(pg_session_factory: Factory) -> None:
    """The last generating design cancelled beside a ready one completes the task."""
    run = await running_task(pg_session_factory)
    await add_design(pg_session_factory, run, BUDDesignStatus.READY)
    last = await add_design(pg_session_factory, run, GENERATING, job_id=run.job_id)

    await _cancel(pg_session_factory, run, last)

    assert await task_state(pg_session_factory, run.task_id) == ("completed", None)


async def test_task_fails_when_nothing_is_ready(pg_session_factory: Factory) -> None:
    """Cancelling the only design fails the task with the reason."""
    run = await running_task(pg_session_factory)
    only = await add_design(pg_session_factory, run, GENERATING, job_id=run.job_id)

    await _cancel(pg_session_factory, run, only)

    assert await task_state(pg_session_factory, run.task_id) == ("failed", "Stopped")


async def test_finished_design_is_not_flipped(pg_session_factory: Factory) -> None:
    """A design that became ready before the cancel landed stays ready."""
    run = await running_task(pg_session_factory)
    ready = await add_design(pg_session_factory, run, BUDDesignStatus.READY)

    assert await _cancel(pg_session_factory, run, ready) == BUDDesignStatus.READY
    assert await task_state(pg_session_factory, run.task_id) == ("completed", None)
