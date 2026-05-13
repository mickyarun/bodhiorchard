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

"""Tests for ``agent_activity_logger.reconcile_orphan_phase_workers``.

Mirrors ``recover_stuck_agent_tasks`` for synthetic phase workers. The
critical invariants:
  - orphan ``skill_invoked`` rows → ``skill_failed`` written + WS published
  - rows already followed by ``skill_completed`` / ``skill_failed`` →
    untouched (no double-emit)
  - clean shutdown with no orphans → no emit, return 0
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services import agent_activity_logger


@pytest.fixture
def fake_db() -> MagicMock:
    db = MagicMock(name="AsyncSession")
    db.execute = AsyncMock()
    return db


def _orphan_row(
    org_id: uuid.UUID, bud_id: uuid.UUID, slug: str = "todo_generator"
) -> SimpleNamespace:
    """Stand-in for an AgentActivityLog row returned by the orphan query."""
    return SimpleNamespace(org_id=org_id, bud_id=bud_id, skill_slug=slug)


@pytest.mark.asyncio
async def test_no_orphans_returns_zero_no_emit(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    monkeypatch.setattr(
        agent_activity_logger,
        "list_orphan_phase_workers",
        AsyncMock(return_value=[]),
    )
    log_call = AsyncMock()
    monkeypatch.setattr(agent_activity_logger, "log_agent_activity", log_call)

    count = await agent_activity_logger.reconcile_orphan_phase_workers(fake_db)

    assert count == 0
    log_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_single_orphan_emits_skill_failed(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    org_id = uuid.uuid4()
    bud_id = uuid.uuid4()
    orphan = _orphan_row(org_id, bud_id, "todo_generator")
    monkeypatch.setattr(
        agent_activity_logger,
        "list_orphan_phase_workers",
        AsyncMock(return_value=[orphan]),
    )
    # BUDDocument lookup returns matching number + title for the bud_id.
    bud_result = MagicMock()
    bud_result.all = MagicMock(
        return_value=[SimpleNamespace(id=bud_id, bud_number=42, title="Test BUD")]
    )
    fake_db.execute = AsyncMock(return_value=bud_result)

    log_call = AsyncMock()
    monkeypatch.setattr(agent_activity_logger, "log_agent_activity", log_call)

    count = await agent_activity_logger.reconcile_orphan_phase_workers(fake_db)

    assert count == 1
    log_call.assert_awaited_once()
    kwargs = log_call.await_args.kwargs
    assert kwargs["event_type"] == "skill_failed"
    assert kwargs["skill_slug"] == "todo_generator"
    assert kwargs["bud_id"] == bud_id
    assert kwargs["bud_number"] == 42
    assert kwargs["bud_title"] == "Test BUD"
    assert kwargs["metadata_"]["reason"] == "server_restart"


@pytest.mark.asyncio
async def test_multiple_orphans_across_orgs_each_emit(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    """Cross-org bulk recovery — each (org, bud, skill) gets its own emit."""
    org_a, org_b = uuid.uuid4(), uuid.uuid4()
    bud_a, bud_b = uuid.uuid4(), uuid.uuid4()
    orphans = [
        _orphan_row(org_a, bud_a, "todo_generator"),
        _orphan_row(org_a, bud_a, "pert_estimator"),
        _orphan_row(org_b, bud_b, "phase_assigner"),
    ]
    monkeypatch.setattr(
        agent_activity_logger,
        "list_orphan_phase_workers",
        AsyncMock(return_value=orphans),
    )
    bud_result = MagicMock()
    bud_result.all = MagicMock(
        return_value=[
            SimpleNamespace(id=bud_a, bud_number=1, title="BUD-A"),
            SimpleNamespace(id=bud_b, bud_number=2, title="BUD-B"),
        ]
    )
    fake_db.execute = AsyncMock(return_value=bud_result)

    log_call = AsyncMock()
    monkeypatch.setattr(agent_activity_logger, "log_agent_activity", log_call)

    count = await agent_activity_logger.reconcile_orphan_phase_workers(fake_db)

    assert count == 3
    assert log_call.await_count == 3
    # Each call carries the matching org_id / bud_id / skill_slug.
    emit_keys = [
        (c.kwargs["org_id"], c.kwargs["bud_id"], c.kwargs["skill_slug"])
        for c in log_call.await_args_list
    ]
    assert (org_a, bud_a, "todo_generator") in emit_keys
    assert (org_a, bud_a, "pert_estimator") in emit_keys
    assert (org_b, bud_b, "phase_assigner") in emit_keys


@pytest.mark.asyncio
async def test_single_bad_emit_does_not_block_others(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    """A failing log_agent_activity for one orphan must not skip the rest."""
    org_id = uuid.uuid4()
    bud_a, bud_b = uuid.uuid4(), uuid.uuid4()
    orphans = [
        _orphan_row(org_id, bud_a, "todo_generator"),
        _orphan_row(org_id, bud_b, "phase_assigner"),
    ]
    monkeypatch.setattr(
        agent_activity_logger,
        "list_orphan_phase_workers",
        AsyncMock(return_value=orphans),
    )
    bud_result = MagicMock()
    bud_result.all = MagicMock(return_value=[])
    fake_db.execute = AsyncMock(return_value=bud_result)

    # First call raises, second succeeds.
    log_call = AsyncMock(side_effect=[RuntimeError("publish boom"), None])
    monkeypatch.setattr(agent_activity_logger, "log_agent_activity", log_call)

    count = await agent_activity_logger.reconcile_orphan_phase_workers(fake_db)

    assert count == 1  # only the successful emit is counted
    assert log_call.await_count == 2  # but both were attempted


@pytest.mark.asyncio
async def test_orphan_without_bud_id_is_skipped(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    """Defensive: rows missing bud_id can't address the WS topic — skip."""
    org_id = uuid.uuid4()
    # bud_id None means we can't form bud:{id}, so the row is unusable.
    orphan = SimpleNamespace(org_id=org_id, bud_id=None, skill_slug="todo_generator")
    monkeypatch.setattr(
        agent_activity_logger,
        "list_orphan_phase_workers",
        AsyncMock(return_value=[orphan]),
    )
    bud_result = MagicMock()
    bud_result.all = MagicMock(return_value=[])
    fake_db.execute = AsyncMock(return_value=bud_result)

    log_call = AsyncMock()
    monkeypatch.setattr(agent_activity_logger, "log_agent_activity", log_call)

    count = await agent_activity_logger.reconcile_orphan_phase_workers(fake_db)

    assert count == 0
    log_call.assert_not_awaited()
