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

"""Unit tests for ``bud_assignment.auto_assign_for_phase``.

The critical invariant: when no users have the target role, the function
publishes a ``skill_failed`` lifecycle event with ``reason=no_candidates``
and returns the existing assignee, **without** calling the smart picker
(which is the only path that can reach an LLM tiebreak).
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bud import BUDStatus
from app.services import bud_assignment


@pytest.fixture
def org_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def fake_db() -> MagicMock:
    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=None)
    return db


def _make_bud() -> SimpleNamespace:
    """Mock BUD with all fields the assignment path reads."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        bud_number=42,
        title="Test BUD",
        assignee_id=None,
        impacted_repos=None,
    )


def _patch_repos(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidates: list[SimpleNamespace],
) -> tuple[AsyncMock, MagicMock]:
    """Stub UserRepository.list_active_with_role and log_agent_activity."""
    list_active = AsyncMock(return_value=candidates)
    user_repo_cls = MagicMock(return_value=MagicMock(list_active_with_role=list_active))
    monkeypatch.setattr(bud_assignment, "UserRepository", user_repo_cls)

    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)

    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))
    return log_activity, user_repo_cls


@pytest.mark.asyncio
async def test_no_candidates_short_circuits_without_smart_call(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """Empty role pool → skill_failed published, smart picker NEVER called."""
    bud = _make_bud()
    log_activity, _ = _patch_repos(monkeypatch, candidates=[])
    # If this gets called for an empty-pool case, the invariant is broken.
    smart = AsyncMock(side_effect=AssertionError("smart picker called with empty pool"))
    monkeypatch.setattr("app.services.smart_assignment.assign_best_for_role", smart)

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, org_id, bud, BUDStatus.DEVELOPMENT
    )

    assert result == bud.assignee_id
    smart.assert_not_called()
    log_activity.assert_awaited_once()
    call_kwargs = log_activity.await_args.kwargs
    assert call_kwargs["event_type"] == "skill_failed"
    assert call_kwargs["skill_slug"] == "phase_assigner"
    assert call_kwargs["metadata_"]["reason"] == "no_candidates"
    assert call_kwargs["metadata_"]["role"] == "developer"


@pytest.mark.asyncio
async def test_smart_match_emits_invoked_then_completed(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """Happy path: invoked → completed with `method=smart_assignment`."""
    bud = _make_bud()
    chosen = SimpleNamespace(id=uuid.uuid4(), name="Alice")
    candidate = SimpleNamespace(id=chosen.id, name="Alice")
    log_activity, _ = _patch_repos(monkeypatch, candidates=[candidate])
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=chosen),
    )

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, org_id, bud, BUDStatus.DEVELOPMENT
    )

    assert result == chosen.id
    assert bud.assignee_id == chosen.id
    # Two events: invoked + completed
    assert log_activity.await_count == 2
    event_types = [c.kwargs["event_type"] for c in log_activity.await_args_list]
    assert event_types == ["skill_invoked", "skill_completed"]
    completed_meta = log_activity.await_args_list[1].kwargs["metadata_"]
    assert completed_meta["method"] == "smart_assignment"


@pytest.mark.asyncio
async def test_smart_returns_none_falls_back_to_round_robin(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """When the smart picker returns None, round-robin from the same pool wins."""
    bud = _make_bud()
    candidate = SimpleNamespace(id=uuid.uuid4(), name="Bob", created_at="2026-01-01")
    log_activity, _ = _patch_repos(monkeypatch, candidates=[candidate])
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=None),
    )
    # Stub the round-robin's workload-count query to a single-entry map.
    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(return_value={})
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))

    result = await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.DESIGN)

    assert result == candidate.id
    completed_meta = log_activity.await_args_list[-1].kwargs["metadata_"]
    assert completed_meta["method"] == "auto_round_robin"


@pytest.mark.parametrize(
    "phase",
    [
        BUDStatus.BUD,
        BUDStatus.DESIGN,
        BUDStatus.TECH_ARCH,
        BUDStatus.DEVELOPMENT,
        BUDStatus.TESTING,
    ],
)
@pytest.mark.asyncio
async def test_all_smart_phases_invoke_skill_picker(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
    phase: BUDStatus,
) -> None:
    """Every role-mapped lifecycle phase must reach the skill-based picker.

    Regression guard: if someone shrinks ``_SMART_ASSIGNMENT_PHASES`` and
    removes one of these, this case fails for that phase.
    """
    bud = _make_bud()
    chosen = SimpleNamespace(id=uuid.uuid4(), name="Pat")
    _patch_repos(monkeypatch, candidates=[SimpleNamespace(id=chosen.id, name="Pat")])
    smart = AsyncMock(return_value=chosen)
    monkeypatch.setattr("app.services.smart_assignment.assign_best_for_role", smart)

    await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, phase)

    smart.assert_awaited_once()


@pytest.mark.asyncio
async def test_code_review_does_not_emit_lifecycle_events(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """CODE_REVIEW retains the developer; no assignment banner should fire."""
    bud = _make_bud()
    bud.assignee_id = uuid.uuid4()
    log_activity, _ = _patch_repos(monkeypatch, candidates=[])

    await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.CODE_REVIEW)

    log_activity.assert_not_called()
