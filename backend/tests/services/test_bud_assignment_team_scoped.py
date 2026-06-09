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

"""Integration tests for team-scoped auto-assignment.

Exercises ``auto_assign_for_phase`` end-to-end (with mocked repos)
to confirm the team-scope filter is wired into the chain walk and
the team-scope provenance flows out onto the lifecycle banner
metadata.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bud import BUDStatus
from app.services import bud_assignment


@pytest.fixture(autouse=True)
def _stub_yield_offer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(bud_assignment, "maybe_raise_yield_offer", AsyncMock(return_value=None))


@pytest.fixture
def fake_db() -> MagicMock:
    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=None)
    db.flush = AsyncMock()
    return db


def _bud(impacted_repos: list[dict[str, str]] | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        bud_number=7,
        title="T",
        assignee_id=None,
        impacted_repos=impacted_repos,
    )


def _patch_chain(
    monkeypatch: pytest.MonkeyPatch,
    *,
    candidates: list[SimpleNamespace],
    team_member_ids: set[uuid.UUID] | None = None,
) -> AsyncMock:
    """Mock the chain walker dependencies + the TeamRepository call."""
    user_repo = MagicMock()
    user_repo.list_active_with_role = AsyncMock(return_value=candidates)
    user_repo.get_role = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "UserRepository", MagicMock(return_value=user_repo))

    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(
        return_value={c.id: 0 for c in candidates}
    )
    bud_repo.weighted_active_loads_for_assignees = AsyncMock(
        return_value={c.id: 0 for c in candidates}
    )
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))

    timeline_repo = MagicMock()
    timeline_repo.latest_assignee_for_phase = AsyncMock(return_value=None)
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=False)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )

    # Mock TeamRepository inside the team_scope module — that's the
    # actual call site once the filter runs.
    from app.services import team_scope as ts

    async def fake_member_ids(self: object, repo_ids: list[uuid.UUID]) -> set[uuid.UUID]:
        return team_member_ids if team_member_ids is not None else set()

    monkeypatch.setattr(ts.TeamRepository, "list_member_ids_for_repos", fake_member_ids)

    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))
    # Don't actually walk into todo assignment in these tests.
    monkeypatch.setattr(bud_assignment, "assign_todos_per_repo_team", AsyncMock(return_value={}))
    # Skip smart assignment so picks land on round-robin (deterministic
    # for assertions).
    monkeypatch.setattr(bud_assignment, "assign_best_for_role", AsyncMock(return_value=None))
    return log_activity


@pytest.mark.asyncio
async def test_no_impacted_repos_skips_filter_and_picks_any_candidate(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    devs = [
        SimpleNamespace(id=uuid.uuid4(), name="Alice", created_at=0),
        SimpleNamespace(id=uuid.uuid4(), name="Bob", created_at=1),
    ]
    log = _patch_chain(monkeypatch, candidates=devs)
    bud = _bud(impacted_repos=None)

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, uuid.uuid4(), bud, BUDStatus.DEVELOPMENT
    )

    assert result == devs[0].id  # least-loaded round-robin → first dev
    # The completed-event metadata always carries team_scope_applied so
    # observers can disambiguate absence from negative.
    completed_call = [
        c for c in log.await_args_list if c.kwargs.get("event_type") == "skill_completed"
    ][-1]
    meta = completed_call.kwargs["metadata_"]
    assert meta["team_scope_applied"] is False
    assert "team_scope_fell_back" not in meta  # only emitted when applied


@pytest.mark.asyncio
async def test_team_scope_narrows_pool_when_impacted_repos_owned_by_team(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    in_team = SimpleNamespace(id=uuid.uuid4(), name="Alice", created_at=0)
    not_in_team = SimpleNamespace(id=uuid.uuid4(), name="Bob", created_at=1)
    log = _patch_chain(
        monkeypatch,
        candidates=[in_team, not_in_team],
        team_member_ids={in_team.id},
    )
    bud = _bud(impacted_repos=[{"repo_id": str(uuid.uuid4()), "repo_name": "x"}])

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, uuid.uuid4(), bud, BUDStatus.DEVELOPMENT
    )

    assert result == in_team.id  # narrowed to the team member
    completed = [
        c for c in log.await_args_list if c.kwargs.get("event_type") == "skill_completed"
    ][-1]
    meta = completed.kwargs["metadata_"]
    assert meta["team_scope_applied"] is True
    assert meta["team_scope_fell_back"] is False
    assert meta["team_scope_impacted_repo_count"] == 1
    assert meta["team_scope_pool_size"] == 1


@pytest.mark.asyncio
async def test_no_team_owns_impacted_repo_falls_back_to_org_wide(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    devs = [
        SimpleNamespace(id=uuid.uuid4(), name="Alice", created_at=0),
        SimpleNamespace(id=uuid.uuid4(), name="Bob", created_at=1),
    ]
    log = _patch_chain(
        monkeypatch,
        candidates=devs,
        team_member_ids=set(),  # no team owns this repo
    )
    bud = _bud(impacted_repos=[{"repo_id": str(uuid.uuid4()), "repo_name": "x"}])

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, uuid.uuid4(), bud, BUDStatus.DEVELOPMENT
    )

    # Fell back to the full pool, picked least-loaded.
    assert result == devs[0].id
    completed = [
        c for c in log.await_args_list if c.kwargs.get("event_type") == "skill_completed"
    ][-1]
    meta = completed.kwargs["metadata_"]
    assert meta["team_scope_applied"] is True
    assert meta["team_scope_fell_back"] is True
    assert meta["team_scope_pool_size"] == 0


@pytest.mark.asyncio
async def test_malformed_impacted_repos_marks_input_malformed(
    monkeypatch: pytest.MonkeyPatch, fake_db: MagicMock
) -> None:
    devs = [SimpleNamespace(id=uuid.uuid4(), name="Alice", created_at=0)]
    log = _patch_chain(monkeypatch, candidates=devs)
    bud = _bud(impacted_repos=[{"repo_id": "garbage"}])

    await bud_assignment.auto_assign_for_phase(fake_db, uuid.uuid4(), bud, BUDStatus.DEVELOPMENT)

    completed = [
        c for c in log.await_args_list if c.kwargs.get("event_type") == "skill_completed"
    ][-1]
    meta = completed.kwargs["metadata_"]
    # applied stays False (we couldn't filter against anything) but
    # the corruption flag fires so admins see the bad data.
    assert meta["team_scope_applied"] is False
    assert meta["team_scope_input_malformed"] is True
    assert meta["team_scope_discarded_count"] == 1
