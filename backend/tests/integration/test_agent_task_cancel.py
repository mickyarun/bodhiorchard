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

"""Cancelling a BUD agent task, on real ``bud_agent_tasks`` / ``bud_designs`` rows.

The in-memory job queue is replaced by two stand-ins: whether the job is
alive, and a recorder for the cancel signal. No agent subprocess exists.
"""

from __future__ import annotations

import uuid

import pytest

from app.models.bud import BUDDesignStatus
from app.models.bud_agent_task import AgentTaskStatus, BUDAgentTask
from app.services import agent_task_cancel
from app.services.agent_task_cancel import AgentTaskCancelError, cancel_task, is_task_terminal
from tests.integration.agent_cancel_support import (
    AgentRun,
    Factory,
    add_design,
    design_status,
    running_task,
    task_state,
)

pytestmark = pytest.mark.integration


def _job_alive(monkeypatch: pytest.MonkeyPatch, alive: bool) -> list[tuple[str, str]]:
    """Pretend the job is (or isn't) running; return the signals sent."""
    signals: list[tuple[str, str]] = []
    monkeypatch.setattr(agent_task_cancel, "is_job_running", lambda job_id: alive)
    monkeypatch.setattr(
        agent_task_cancel,
        "cancel_in_memory_job",
        lambda job_id, reason: signals.append((job_id, reason)) or True,
    )
    return signals


async def _cancel(factory: Factory, run: AgentRun, org_id: uuid.UUID | None = None) -> str:
    async with factory() as db:
        task = await db.get(BUDAgentTask, run.task_id)
        assert task is not None
        fresh = await cancel_task(db, org_id=org_id or run.org_id, task=task, reason="Stopped")
        return fresh.status


async def test_orphan_task_after_restart_is_failed_without_a_signal(
    monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory
) -> None:
    """No live job (backend restarted): rows are failed and nothing is signalled."""
    signals = _job_alive(monkeypatch, alive=False)
    run = await running_task(pg_session_factory)
    design = await add_design(
        pg_session_factory, run, BUDDesignStatus.GENERATING, job_id=run.job_id
    )

    assert await _cancel(pg_session_factory, run) == AgentTaskStatus.FAILED

    assert signals == []
    assert await task_state(pg_session_factory, run.task_id) == ("failed", "Stopped")
    assert await design_status(pg_session_factory, design) == BUDDesignStatus.FAILED


async def test_live_job_is_signalled_with_the_reason(
    monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory
) -> None:
    """A running job gets the cancel signal before the rows are failed."""
    signals = _job_alive(monkeypatch, alive=True)
    run = await running_task(pg_session_factory)

    await _cancel(pg_session_factory, run)

    assert signals == [(run.job_id, "Stopped")]
    assert await task_state(pg_session_factory, run.task_id) == ("failed", "Stopped")


async def test_failed_signal_writes_nothing(
    monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory
) -> None:
    """If the live job can't be signalled, the task stays running (spinner honest)."""
    monkeypatch.setattr(agent_task_cancel, "is_job_running", lambda job_id: True)

    def _refuse(job_id: str, reason: str) -> bool:
        raise RuntimeError("queue gone")

    monkeypatch.setattr(agent_task_cancel, "cancel_in_memory_job", _refuse)
    run = await running_task(pg_session_factory)

    with pytest.raises(AgentTaskCancelError, match="queue gone"):
        await _cancel(pg_session_factory, run)

    assert await task_state(pg_session_factory, run.task_id) == ("running", None)


async def test_task_that_finished_first_keeps_its_result(
    monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory
) -> None:
    """A cancel racing a normal finish must not overwrite COMPLETED or READY."""
    _job_alive(monkeypatch, alive=False)
    run = await running_task(pg_session_factory)
    design = await add_design(pg_session_factory, run, BUDDesignStatus.READY, job_id=run.job_id)
    async with pg_session_factory() as db:
        task = await db.get(BUDAgentTask, run.task_id)
        assert task is not None
        task.status = AgentTaskStatus.COMPLETED
        await db.commit()

    assert await _cancel(pg_session_factory, run) == AgentTaskStatus.COMPLETED
    assert await design_status(pg_session_factory, design) == BUDDesignStatus.READY


async def test_cancel_under_another_org_changes_nothing(
    monkeypatch: pytest.MonkeyPatch, pg_session_factory: Factory
) -> None:
    """The tenant-scoped writes ignore a task that isn't the given org's."""
    _job_alive(monkeypatch, alive=False)
    run = await running_task(pg_session_factory)
    other = await running_task(pg_session_factory)
    design = await add_design(
        pg_session_factory, run, BUDDesignStatus.GENERATING, job_id=run.job_id
    )

    await _cancel(pg_session_factory, run, org_id=other.org_id)

    assert await task_state(pg_session_factory, run.task_id) == ("running", None)
    assert await design_status(pg_session_factory, design) == BUDDesignStatus.GENERATING


@pytest.mark.parametrize(
    ("status", "terminal"),
    [("pending", False), ("running", False), ("completed", True), ("failed", True)],
)
def test_is_task_terminal(status: str, terminal: bool) -> None:
    """Only pending and running tasks can be cancelled."""
    assert is_task_terminal(BUDAgentTask(status=status)) is terminal
