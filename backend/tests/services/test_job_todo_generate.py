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

"""Tests for the ``todo_generate`` job handler.

Patches ``AsyncSessionLocal``, ``BUDRepository``, ``sync_todos_for_bud``,
``publish``, and ``update_job`` so the suite never spawns a real Claude
subprocess or touches the DB. Exercises the contract: status state
transitions, event publishes on success / failure, missing-bud path.
"""

import uuid
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.schemas.jobs import JobState
from app.services import job_todo_generate


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def bud_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def payload(org_id: uuid.UUID, bud_id: uuid.UUID) -> dict[str, Any]:
    return {"org_id": str(org_id), "bud_id": str(bud_id), "mode": "initial"}


def _patch_session(monkeypatch: pytest.MonkeyPatch) -> MagicMock:
    fake_db = MagicMock(name="AsyncSession")
    fake_db.commit = AsyncMock()
    fake_db.rollback = AsyncMock()

    @asynccontextmanager
    async def _ctx() -> Any:
        yield fake_db

    monkeypatch.setattr(job_todo_generate, "AsyncSessionLocal", _ctx)
    return fake_db


def _patch_repo(monkeypatch: pytest.MonkeyPatch, bud: object | None) -> None:
    fake_repo = MagicMock(name="BUDRepository")
    fake_repo.get_by_id = AsyncMock(return_value=bud)
    monkeypatch.setattr(job_todo_generate, "BUDRepository", MagicMock(return_value=fake_repo))


def _spies(
    monkeypatch: pytest.MonkeyPatch,
    *,
    assign: AsyncMock | None = None,
) -> tuple[MagicMock, MagicMock]:
    publish = MagicMock()
    update_job = MagicMock()
    monkeypatch.setattr(job_todo_generate, "publish", publish)
    monkeypatch.setattr(job_todo_generate, "update_job", update_job)
    # Estimation is exercised by its own suite — stub it to a no-op here.
    monkeypatch.setattr(job_todo_generate, "estimate_bud_dates", AsyncMock(return_value={}))
    monkeypatch.setattr(
        job_todo_generate,
        "assign_all_todos_to_lead",
        assign or AsyncMock(return_value=0),
    )
    # Lifecycle event publish is exercised by its own suite — stub here so
    # the SimpleNamespace fixtures don't need to mock the full SQLAlchemy
    # session that `log_agent_activity` writes through.
    monkeypatch.setattr(job_todo_generate, "log_agent_activity", AsyncMock(return_value=None))
    return publish, update_job


def _make_bud(bud_id: uuid.UUID, *, assignee_id: uuid.UUID | None = None) -> SimpleNamespace:
    """Mock BUD with the fields the worker reads (id, assignee_id, bud_number, title)."""
    return SimpleNamespace(
        id=bud_id,
        assignee_id=assignee_id,
        bud_number=42,
        title="Test BUD",
    )


# ── happy path ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_happy_path_publishes_and_completes(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    bud_id: uuid.UUID,
) -> None:
    fake_db = _patch_session(monkeypatch)
    fake_db.refresh = AsyncMock()
    # No lead set — assignment branch is skipped.
    bud = _make_bud(bud_id)
    _patch_repo(monkeypatch, bud)
    sync = AsyncMock(return_value=7)
    monkeypatch.setattr(job_todo_generate, "sync_todos_for_bud", sync)
    publish, update_job = _spies(monkeypatch)

    await job_todo_generate.handle_todo_generate_job("job-1", payload)

    sync.assert_awaited_once_with(fake_db, uuid.UUID(payload["org_id"]), bud, mode="initial")
    # Two commits: one after sync, one after estimation.
    assert fake_db.commit.await_count == 2
    publish.assert_called_once_with(
        f"todo:{bud_id}",
        {"event": "todos_regenerated", "bud_id": str(bud_id), "todo_count": 7},
    )
    # RUNNING → RUNNING (estimation phase) → COMPLETED.
    states = [c.kwargs.get("state") for c in update_job.call_args_list if c.kwargs.get("state")]
    assert states == [JobState.RUNNING, JobState.RUNNING, JobState.COMPLETED]


@pytest.mark.asyncio
async def test_initial_mode_assigns_todos_to_lead_after_sync(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    bud_id: uuid.UUID,
    org_id: uuid.UUID,
) -> None:
    """Lead assignment runs after sync commit — preserves pre-job-queue invariant."""
    fake_db = _patch_session(monkeypatch)
    fake_db.refresh = AsyncMock()
    lead_id = uuid.uuid4()
    bud = _make_bud(bud_id, assignee_id=lead_id)
    _patch_repo(monkeypatch, bud)
    monkeypatch.setattr(job_todo_generate, "sync_todos_for_bud", AsyncMock(return_value=4))
    assign = AsyncMock(return_value=4)
    _spies(monkeypatch, assign=assign)

    await job_todo_generate.handle_todo_generate_job("job-a", payload)

    fake_db.refresh.assert_awaited_once_with(bud, ["assignee_id"])
    assign.assert_awaited_once_with(fake_db, org_id, bud_id, lead_id)
    # Three commits now: sync, lead-assign, estimation.
    assert fake_db.commit.await_count == 3


@pytest.mark.asyncio
async def test_regenerate_mode_skips_lead_assignment(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    bud_id: uuid.UUID,
) -> None:
    """Regenerate (user-triggered) must not steal TODOs from developers."""
    fake_db = _patch_session(monkeypatch)
    fake_db.refresh = AsyncMock()
    bud = _make_bud(bud_id, assignee_id=uuid.uuid4())
    _patch_repo(monkeypatch, bud)
    monkeypatch.setattr(job_todo_generate, "sync_todos_for_bud", AsyncMock(return_value=4))
    assign = AsyncMock()
    _spies(monkeypatch, assign=assign)

    await job_todo_generate.handle_todo_generate_job("job-b", {**payload, "mode": "regenerate"})

    assign.assert_not_awaited()
    fake_db.refresh.assert_not_awaited()


# ── failure modes ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_missing_bud_marks_job_failed(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    bud_id: uuid.UUID,
) -> None:
    _patch_session(monkeypatch)
    _patch_repo(monkeypatch, None)
    sync = AsyncMock()
    monkeypatch.setattr(job_todo_generate, "sync_todos_for_bud", sync)
    publish, update_job = _spies(monkeypatch)

    await job_todo_generate.handle_todo_generate_job("job-2", payload)

    sync.assert_not_awaited()
    publish.assert_called_once_with(
        f"todo:{bud_id}",
        {"event": "generating_failed", "error": f"BUD {bud_id} not found"},
    )
    states = [c.kwargs.get("state") for c in update_job.call_args_list if c.kwargs.get("state")]
    assert states[-1] == JobState.FAILED


@pytest.mark.asyncio
async def test_sync_exception_rolls_back_and_publishes_failed(
    monkeypatch: pytest.MonkeyPatch,
    payload: dict[str, Any],
    bud_id: uuid.UUID,
) -> None:
    fake_db = _patch_session(monkeypatch)
    bud = _make_bud(bud_id)
    _patch_repo(monkeypatch, bud)
    monkeypatch.setattr(
        job_todo_generate,
        "sync_todos_for_bud",
        AsyncMock(side_effect=RuntimeError("agent boom")),
    )
    publish, update_job = _spies(monkeypatch)

    await job_todo_generate.handle_todo_generate_job("job-3", payload)

    fake_db.rollback.assert_awaited_once()
    fake_db.commit.assert_not_awaited()
    publish.assert_called_once_with(
        f"todo:{bud_id}",
        {"event": "generating_failed", "error": "agent boom"},
    )
    states = [c.kwargs.get("state") for c in update_job.call_args_list if c.kwargs.get("state")]
    assert states[-1] == JobState.FAILED
