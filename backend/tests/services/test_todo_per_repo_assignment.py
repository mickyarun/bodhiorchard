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

"""Unit tests for ``todo_assignment.assign_todos_per_repo_team``.

Heavy mocking of repository layer — the function's job is to route
TODOs into the correct buckets (team_scoped / lead_fallback / sub-
buckets) based on what the repo + team lookups return. The mocks make
that wiring directly testable without spinning up a DB.
"""

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.user import UserRole
from app.services import todo_assignment


def _todo(repo_name: str | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        repo_name=repo_name,
        assignee_id=None,
    )


def _user(uid: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(id=uid or uuid.uuid4())


def _patch_repos(
    monkeypatch: pytest.MonkeyPatch,
    *,
    unassigned: list[SimpleNamespace],
    repo_lookup: dict[str, SimpleNamespace | None],
    team_members_for_repo: dict[uuid.UUID, set[uuid.UUID]],
    developer_pool: list[SimpleNamespace],
    load_map: dict[uuid.UUID, int] | None = None,
) -> None:
    """Mock every repository call ``assign_todos_per_repo_team`` makes."""
    monkeypatch.setattr(
        todo_assignment,
        "_list_unassigned_non_checkpoint_todos",
        AsyncMock(return_value=unassigned),
    )

    fake_repo_repo = MagicMock()
    fake_repo_repo.get_by_name = AsyncMock(side_effect=lambda name: repo_lookup.get(name))
    monkeypatch.setattr(todo_assignment, "TrackedRepoRepository", lambda *a, **k: fake_repo_repo)

    fake_team_repo = MagicMock()
    fake_team_repo.list_member_ids_for_repos = AsyncMock(
        side_effect=lambda repo_ids: team_members_for_repo.get(repo_ids[0], set())
    )
    monkeypatch.setattr(todo_assignment, "TeamRepository", lambda *a, **k: fake_team_repo)

    fake_user_repo = MagicMock()
    fake_user_repo.list_active_with_role = AsyncMock(return_value=developer_pool)
    monkeypatch.setattr(todo_assignment, "UserRepository", lambda *a, **k: fake_user_repo)

    fake_bud_repo = MagicMock()
    fake_bud_repo.count_active_loads_for_assignees = AsyncMock(return_value=load_map or {})
    monkeypatch.setattr(todo_assignment, "BUDRepository", lambda *a, **k: fake_bud_repo)


def _fake_db() -> MagicMock:
    db = MagicMock(name="AsyncSession")
    db.flush = AsyncMock()
    return db


@pytest.mark.asyncio
async def test_no_unassigned_todos_returns_zero_buckets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_repos(
        monkeypatch,
        unassigned=[],
        repo_lookup={},
        team_members_for_repo={},
        developer_pool=[],
    )
    result = await todo_assignment.assign_todos_per_repo_team(
        _fake_db(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    )
    assert sum(result.values()) == 0


@pytest.mark.asyncio
async def test_todo_without_repo_name_goes_to_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = uuid.uuid4()
    todo = _todo(repo_name=None)
    _patch_repos(
        monkeypatch,
        unassigned=[todo],
        repo_lookup={},
        team_members_for_repo={},
        developer_pool=[],
    )
    result = await todo_assignment.assign_todos_per_repo_team(
        _fake_db(), uuid.uuid4(), uuid.uuid4(), lead
    )
    assert todo.assignee_id == lead
    assert result["skipped_no_repo_name"] == 1
    assert result["lead_fallback"] == 1
    assert result["team_scoped"] == 0


@pytest.mark.asyncio
async def test_unknown_repo_name_falls_back_to_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = uuid.uuid4()
    todo = _todo(repo_name="unknown-repo")
    _patch_repos(
        monkeypatch,
        unassigned=[todo],
        repo_lookup={"unknown-repo": None},  # not found
        team_members_for_repo={},
        developer_pool=[],
    )
    result = await todo_assignment.assign_todos_per_repo_team(
        _fake_db(), uuid.uuid4(), uuid.uuid4(), lead
    )
    assert todo.assignee_id == lead
    assert result["no_repo_match"] == 1
    assert result["lead_fallback"] == 1


@pytest.mark.asyncio
async def test_repo_with_no_owning_team_falls_back_to_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = uuid.uuid4()
    repo = SimpleNamespace(id=uuid.uuid4(), name="orphan-repo")
    todo = _todo(repo_name="orphan-repo")
    _patch_repos(
        monkeypatch,
        unassigned=[todo],
        repo_lookup={"orphan-repo": repo},
        team_members_for_repo={repo.id: set()},  # no team
        developer_pool=[_user()],
    )
    result = await todo_assignment.assign_todos_per_repo_team(
        _fake_db(), uuid.uuid4(), uuid.uuid4(), lead
    )
    assert todo.assignee_id == lead
    assert result["no_team"] == 1
    assert result["no_dev_in_team"] == 0


@pytest.mark.asyncio
async def test_team_with_no_active_developer_falls_back_to_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = uuid.uuid4()
    repo = SimpleNamespace(id=uuid.uuid4(), name="frontend")
    todo = _todo(repo_name="frontend")
    # Team has a member but it's not in the developer pool
    team_member_only = uuid.uuid4()
    _patch_repos(
        monkeypatch,
        unassigned=[todo],
        repo_lookup={"frontend": repo},
        team_members_for_repo={repo.id: {team_member_only}},
        developer_pool=[_user()],  # different person
    )
    result = await todo_assignment.assign_todos_per_repo_team(
        _fake_db(), uuid.uuid4(), uuid.uuid4(), lead
    )
    assert todo.assignee_id == lead
    assert result["no_dev_in_team"] == 1


@pytest.mark.asyncio
async def test_happy_path_distributes_todos_across_repo_team_devs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = uuid.uuid4()
    repo = SimpleNamespace(id=uuid.uuid4(), name="backend")
    dev_a = _user()
    dev_b = _user()
    todos = [_todo("backend") for _ in range(5)]

    _patch_repos(
        monkeypatch,
        unassigned=todos,
        repo_lookup={"backend": repo},
        team_members_for_repo={repo.id: {dev_a.id, dev_b.id}},
        developer_pool=[dev_a, dev_b],
        load_map={dev_a.id: 0, dev_b.id: 0},
    )

    result = await todo_assignment.assign_todos_per_repo_team(
        _fake_db(), uuid.uuid4(), uuid.uuid4(), lead
    )
    assert result["team_scoped"] == 5
    assert result["lead_fallback"] == 0
    # Round-robin across 2 devs → both should appear in the assignees.
    assigned = {t.assignee_id for t in todos}
    assert assigned == {dev_a.id, dev_b.id}


@pytest.mark.asyncio
async def test_least_loaded_dev_wins_first_pick(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lead = uuid.uuid4()
    repo = SimpleNamespace(id=uuid.uuid4(), name="backend")
    busy = _user()
    free = _user()
    todos = [_todo("backend"), _todo("backend")]

    _patch_repos(
        monkeypatch,
        unassigned=todos,
        repo_lookup={"backend": repo},
        team_members_for_repo={repo.id: {busy.id, free.id}},
        developer_pool=[busy, free],
        # busy has 5 active, free has 0 — free should get first todo
        load_map={busy.id: 5, free.id: 0},
    )
    await todo_assignment.assign_todos_per_repo_team(_fake_db(), uuid.uuid4(), uuid.uuid4(), lead)
    assert todos[0].assignee_id == free.id
    # Second todo round-robins to the other dev (busy)
    assert todos[1].assignee_id == busy.id


@pytest.mark.asyncio
async def test_mixed_per_repo_and_no_repo_todos(monkeypatch: pytest.MonkeyPatch) -> None:
    lead = uuid.uuid4()
    backend = SimpleNamespace(id=uuid.uuid4(), name="backend")
    frontend = SimpleNamespace(id=uuid.uuid4(), name="frontend")
    dev_backend = _user()
    dev_frontend = _user()
    todos = [
        _todo("backend"),
        _todo("frontend"),
        _todo(None),  # no repo name → lead
    ]

    _patch_repos(
        monkeypatch,
        unassigned=todos,
        repo_lookup={"backend": backend, "frontend": frontend},
        team_members_for_repo={
            backend.id: {dev_backend.id},
            frontend.id: {dev_frontend.id},
        },
        developer_pool=[dev_backend, dev_frontend],
    )
    result = await todo_assignment.assign_todos_per_repo_team(
        _fake_db(), uuid.uuid4(), uuid.uuid4(), lead
    )
    assert todos[0].assignee_id == dev_backend.id
    assert todos[1].assignee_id == dev_frontend.id
    assert todos[2].assignee_id == lead
    assert result["team_scoped"] == 2
    assert result["skipped_no_repo_name"] == 1
    assert result["lead_fallback"] == 1


# UserRole enum smoke-import — guards against an accidental string typo
# in the call to ``list_active_with_role`` somewhere down the line.
def test_role_enum_value_is_developer() -> None:
    assert UserRole.DEVELOPER.value == "developer"
