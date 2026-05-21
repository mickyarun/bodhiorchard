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

Three outcomes the handler must distinguish at the structured-resolver
layer:

- ``ok`` → smart-or-round-robin assignment proceeds.
- ``no_candidates`` → ``skill_failed`` published, no smart call.
- ``all_at_capacity`` → ``skill_failed`` with reason=``all_at_capacity``,
  no smart call, BUD stays unassigned. This is the layer-2 guarantee
  the user asked for: "if max_count reaches keep it unassigned".
"""

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bud import BUDStatus
from app.models.user import UserRole
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
    load_map: dict[uuid.UUID, int] | None = None,
    continuity_hit: tuple[uuid.UUID, Any, str] | None = None,
    later_user_unassign: bool = False,
) -> AsyncMock:
    """Patch the repos + log_agent_activity used by auto_assign_for_phase.

    - ``candidates`` is what ``UserRepository.list_active_with_role`` returns.
    - ``load_map`` defaults to zero-load per candidate.
    - ``continuity_hit`` injects a previous-assignee tuple
      ``(user_id, assigned_at, role_value)`` so tests can exercise the
      continuity path. Default ``None`` → no prior history.
    - ``later_user_unassign`` simulates a deliberate human unassign
      after the continuity-hit assignment (suppresses continuity).
    """
    list_active = AsyncMock(return_value=candidates)
    user_repo_cls = MagicMock(
        return_value=MagicMock(
            list_active_with_role=list_active,
            # CODE_REVIEW retention now resolves the actual role of the
            # held-over developer (or fallback tech_lead) — default None
            # is fine for tests that don't care.
            get_role=AsyncMock(return_value=None),
        )
    )
    monkeypatch.setattr(bud_assignment, "UserRepository", user_repo_cls)

    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(
        return_value=load_map if load_map is not None else {c.id: 0 for c in candidates}
    )
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))

    timeline_repo = MagicMock()
    timeline_repo.latest_assignee_for_phase = AsyncMock(return_value=continuity_hit)
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=later_user_unassign)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )

    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))
    return log_activity


@pytest.mark.asyncio
async def test_no_candidates_short_circuits_and_clears_stale_assignee(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """Empty role pool → skill_failed, smart never called, BUD unassigned.

    A previous assignee from an earlier phase (or a manual assignment)
    must be cleared, otherwise the avatar stays on the BUD while the
    banner says "assignment skipped" — confusing and a real-world bug.
    """
    bud = _make_bud()
    bud.assignee_id = uuid.uuid4()  # stale previous assignment
    log_activity = _patch_repos(monkeypatch, candidates=[])
    smart = AsyncMock(side_effect=AssertionError("smart picker called with empty pool"))
    monkeypatch.setattr("app.services.smart_assignment.assign_best_for_role", smart)

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, org_id, bud, BUDStatus.DEVELOPMENT
    )

    assert result is None
    assert bud.assignee_id is None  # stale assignee cleared
    smart.assert_not_called()
    log_activity.assert_awaited_once()
    call_kwargs = log_activity.await_args.kwargs
    assert call_kwargs["event_type"] == "skill_failed"
    assert call_kwargs["metadata_"]["reason"] == "no_candidates"
    assert call_kwargs["metadata_"]["role"] == "developer"
    assert call_kwargs["metadata_"]["chain"] == ["developer", "tech_lead"]


@pytest.mark.asyncio
async def test_all_at_capacity_emits_warning_and_leaves_unassigned(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """When every developer is at the role's cap → skill_failed reason=all_at_capacity.

    User's stated rule: "if max_count reaches keep it unassigned". The
    handler must NOT fall through to a different role just because the
    primary is busy, and the smart picker must never run.
    """
    bud = _make_bud()
    devs = [SimpleNamespace(id=uuid.uuid4(), name=f"Dev{i}") for i in range(2)]

    # Role-aware mock: only DEVELOPER has members; fallback roles return
    # empty so the chain walk doesn't silently route around capacity.
    async def list_active(_org_id: uuid.UUID, role: object) -> list[SimpleNamespace]:
        return devs if role == UserRole.DEVELOPER else []

    user_repo_cls = MagicMock(
        return_value=MagicMock(list_active_with_role=AsyncMock(side_effect=list_active))
    )
    monkeypatch.setattr(bud_assignment, "UserRepository", user_repo_cls)

    cap = bud_assignment.max_active_buds_for(UserRole.DEVELOPER)
    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(
        return_value={d.id: cap for d in devs}  # exactly at cap → excluded
    )
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))

    timeline_repo = MagicMock()
    timeline_repo.latest_assignee_for_phase = AsyncMock(return_value=None)
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=False)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )

    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))
    smart = AsyncMock(side_effect=AssertionError("smart picker called when all at cap"))
    monkeypatch.setattr("app.services.smart_assignment.assign_best_for_role", smart)

    bud.assignee_id = uuid.uuid4()  # stale prior assignment to clear

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, org_id, bud, BUDStatus.DEVELOPMENT
    )

    assert result is None
    assert bud.assignee_id is None  # at-capacity clears the avatar
    smart.assert_not_called()
    log_activity.assert_awaited_once()
    meta = log_activity.await_args.kwargs["metadata_"]
    assert meta["reason"] == "all_at_capacity"
    assert meta["role"] == "developer"
    assert meta["capacity"] == cap
    assert meta["count"] == len(devs)


@pytest.mark.asyncio
async def test_pm_cap_strictly_higher_than_developer_cap(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """PMs juggle more BUDs than devs — the per-role dict must reflect it.

    Pins explicit caps for the duration of the test so the assertion
    isn't fragile against the live source values (which a developer
    might temporarily tweak when debugging — see commit messages).
    """
    monkeypatch.setitem(bud_assignment.MAX_ACTIVE_BUDS_PER_ROLE, UserRole.PM, 10)
    monkeypatch.setitem(bud_assignment.MAX_ACTIVE_BUDS_PER_ROLE, UserRole.DEVELOPER, 3)
    pm_cap = bud_assignment.max_active_buds_for(UserRole.PM)
    dev_cap = bud_assignment.max_active_buds_for(UserRole.DEVELOPER)
    assert pm_cap > dev_cap

    # PM at one-less-than-cap is still eligible → assigned, not skipped.
    bud = _make_bud()
    pm = SimpleNamespace(id=uuid.uuid4(), name="Priya", created_at="2026-01-01")
    _patch_repos(monkeypatch, candidates=[pm], load_map={pm.id: pm_cap - 1})
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=pm),
    )

    result = await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.BUD)
    assert result == pm.id


@pytest.mark.asyncio
async def test_fallback_role_used_when_primary_empty(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """Tech-arch chain: empty tech_lead pool → fallback to developer wins."""
    bud = _make_bud()
    developer = SimpleNamespace(id=uuid.uuid4(), name="Carol", created_at="2026-01-01")
    role_order: list[str] = []

    async def list_active(_org_id: uuid.UUID, role: object) -> list[SimpleNamespace]:
        role_order.append(str(role))
        return [] if str(role) == "tech_lead" else [developer]

    user_repo_cls = MagicMock(
        return_value=MagicMock(list_active_with_role=AsyncMock(side_effect=list_active))
    )
    monkeypatch.setattr(bud_assignment, "UserRepository", user_repo_cls)

    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(return_value={developer.id: 0})
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))

    timeline_repo = MagicMock()
    timeline_repo.latest_assignee_for_phase = AsyncMock(return_value=None)
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=False)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )

    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=developer),
    )

    result = await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.TECH_ARCH)

    assert result == developer.id
    assert role_order == ["tech_lead", "developer"]
    # invoked + completed both carry the fallback metadata.
    assert log_activity.await_count == 2
    for call in log_activity.await_args_list:
        meta = call.kwargs["metadata_"]
        assert meta["assignment_via_fallback"] is True
        assert meta["fallback_from"] == "tech_lead"
        assert meta["fallback_to"] == "developer"


@pytest.mark.asyncio
async def test_smart_match_emits_invoked_then_completed(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """Happy path: invoked → completed with method=smart_assignment."""
    bud = _make_bud()
    candidate = SimpleNamespace(id=uuid.uuid4(), name="Alice", created_at="2026-01-01")
    log_activity = _patch_repos(monkeypatch, candidates=[candidate])
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=candidate),
    )

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, org_id, bud, BUDStatus.DEVELOPMENT
    )

    assert result == candidate.id
    assert bud.assignee_id == candidate.id
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
    log_activity = _patch_repos(monkeypatch, candidates=[candidate])
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=None),
    )

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
    """Every role-mapped lifecycle phase must reach the skill-based picker."""
    bud = _make_bud()
    candidate = SimpleNamespace(id=uuid.uuid4(), name="Pat", created_at="2026-01-01")
    _patch_repos(monkeypatch, candidates=[candidate])
    smart = AsyncMock(return_value=candidate)
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
    log_activity = _patch_repos(monkeypatch, candidates=[])

    await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.CODE_REVIEW)

    log_activity.assert_not_called()


# ── Continuity (timeline-driven previous-assignee preference) ──────────


def _continuity_hit(user_id: uuid.UUID, role: str = "pm") -> tuple[uuid.UUID, datetime, str]:
    """Build a fake ``latest_assignee_for_phase`` return value."""
    return (user_id, datetime(2026, 5, 14, tzinfo=UTC), role)


def _patch_continuity_world(
    monkeypatch: pytest.MonkeyPatch,
    *,
    prev_user: SimpleNamespace,
    prev_role: UserRole = UserRole.PM,
    is_active: bool = True,
    later_unassign: bool = False,
    members_with_role: list[SimpleNamespace] | None = None,
    load_for_prev: int = 0,
    skill_pick: SimpleNamespace | None = None,
) -> AsyncMock:
    """Set up the world so the continuity helper has everything it needs.

    Builds a coherent set of mocks: timeline returns the hit, db.get
    returns the user with the configured ``is_active``, the user role
    lookup membership returns the user under their previous role, and
    BUD load_map can reflect over/under cap.
    """
    members = members_with_role if members_with_role is not None else [prev_user]

    async def list_active(_org_id: uuid.UUID, role: object) -> list[SimpleNamespace]:
        # Membership query: return the user only under their previous
        # role (so the role-eligibility check inside the helper passes
        # iff prev_role is in the chain).
        return members if role == prev_role else []

    monkeypatch.setattr(
        bud_assignment,
        "UserRepository",
        MagicMock(
            return_value=MagicMock(list_active_with_role=AsyncMock(side_effect=list_active))
        ),
    )

    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(
        return_value={prev_user.id: load_for_prev}
    )
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))

    timeline_repo = MagicMock()
    timeline_repo.latest_assignee_for_phase = AsyncMock(
        return_value=_continuity_hit(prev_user.id, prev_role.value)
    )
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=later_unassign)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )

    # db.get(User, id) returns our prev_user with the configured active flag.
    prev_user.is_active = is_active
    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))

    if skill_pick is not None:
        monkeypatch.setattr(
            "app.services.smart_assignment.assign_best_for_role",
            AsyncMock(return_value=skill_pick),
        )
    return log_activity


@pytest.mark.asyncio
async def test_continuity_reassigns_previous_assignee_when_eligible(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
) -> None:
    """Prior PM assignment + still active + under cap → reassigned with method=continuity."""
    prev = SimpleNamespace(id=uuid.uuid4(), name="Priya", email="p@x", created_at="2026-01-01")
    log_activity = _patch_continuity_world(monkeypatch, prev_user=prev)

    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=prev)
    bud = _make_bud()
    bud.assignee_id = None

    result = await bud_assignment.auto_assign_for_phase(db, org_id, bud, BUDStatus.BUD)

    assert result == prev.id
    assert bud.assignee_id == prev.id
    # invoked + completed are both emitted (matches smart-path banner pattern).
    assert log_activity.await_count == 2
    types = [c.kwargs["event_type"] for c in log_activity.await_args_list]
    assert types == ["skill_invoked", "skill_completed"]
    completed = log_activity.await_args_list[-1].kwargs["metadata_"]
    assert completed["method"] == "continuity"
    assert completed["continuity_from_role"] == "pm"


@pytest.mark.asyncio
async def test_continuity_skipped_when_previous_assignee_inactive(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
) -> None:
    """Prior assignee with ``is_active=False`` → continuity miss, fall through to chain."""
    prev = SimpleNamespace(id=uuid.uuid4(), name="ExPM", email="e@x", created_at="2026-01-01")
    # No other PMs in the org, so the chain falls through to no_candidates
    # (the prev user fails active check; chain returns no fallbacks here).
    log_activity = _patch_continuity_world(
        monkeypatch,
        prev_user=prev,
        is_active=False,
        members_with_role=[],  # nobody currently holds the role
    )

    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=prev)
    bud = _make_bud()

    await bud_assignment.auto_assign_for_phase(db, org_id, bud, BUDStatus.BUD)

    # Continuity didn't fire → no skill_invoked from continuity path; the
    # only event is the no_candidates skill_failed from the chain walk.
    types = [c.kwargs["event_type"] for c in log_activity.await_args_list]
    assert "skill_invoked" not in types
    assert types == ["skill_failed"]
    assert log_activity.await_args.kwargs["metadata_"]["reason"] == "no_candidates"


@pytest.mark.asyncio
async def test_continuity_skipped_when_previous_assignee_over_cap(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
) -> None:
    """Prior assignee at role cap → continuity miss, normal flow takes over."""
    monkeypatch.setitem(bud_assignment.MAX_ACTIVE_BUDS_PER_ROLE, UserRole.PM, 3)
    prev = SimpleNamespace(id=uuid.uuid4(), name="BusyPM", email="b@x", created_at="2026-01-01")
    # prev is the only PM, but their load equals the cap → over.
    fresh_pick = SimpleNamespace(
        id=uuid.uuid4(), name="FreshPM", email="f@x", created_at="2026-02-01"
    )
    log_activity = _patch_continuity_world(
        monkeypatch,
        prev_user=prev,
        load_for_prev=3,
        # The chain walk that runs AFTER continuity miss won't see prev
        # (membership returns just prev under PM, but they're over cap
        # → all_at_capacity). We only assert continuity didn't fire.
        skill_pick=fresh_pick,
    )

    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=prev)
    bud = _make_bud()

    await bud_assignment.auto_assign_for_phase(db, org_id, bud, BUDStatus.BUD)

    # The continuity-success path emits "Reassigning … (continuity)"; we
    # assert that message never went out.
    messages = [c.kwargs.get("message", "") for c in log_activity.await_args_list]
    assert not any("continuity" in m.lower() for m in messages)


@pytest.mark.asyncio
async def test_continuity_skipped_when_previous_assignee_role_changed(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
) -> None:
    """Prior assignee no longer holds an eligible role → continuity miss."""
    prev = SimpleNamespace(id=uuid.uuid4(), name="MovedOn", email="m@x", created_at="2026-01-01")
    # Their PREVIOUS role was PM, but they no longer hold ANY role in the
    # chain — simulate by returning empty members for every role.
    log_activity = _patch_continuity_world(
        monkeypatch,
        prev_user=prev,
        members_with_role=[],
    )

    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=prev)
    bud = _make_bud()

    await bud_assignment.auto_assign_for_phase(db, org_id, bud, BUDStatus.BUD)

    messages = [c.kwargs.get("message", "") for c in log_activity.await_args_list]
    assert not any("continuity" in m.lower() for m in messages)


@pytest.mark.asyncio
async def test_continuity_respects_explicit_user_unassign(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
) -> None:
    """A human unassign after the prior assignment suppresses continuity."""
    prev = SimpleNamespace(id=uuid.uuid4(), name="OldPick", email="o@x", created_at="2026-01-01")
    log_activity = _patch_continuity_world(
        monkeypatch,
        prev_user=prev,
        later_unassign=True,  # someone deliberately removed them
    )

    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=prev)
    bud = _make_bud()

    await bud_assignment.auto_assign_for_phase(db, org_id, bud, BUDStatus.BUD)

    messages = [c.kwargs.get("message", "") for c in log_activity.await_args_list]
    assert not any("continuity" in m.lower() for m in messages)


@pytest.mark.asyncio
async def test_continuity_no_history_falls_through(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """No prior ``assigned`` event for this BUD → normal smart-assign flow."""
    bud = _make_bud()
    candidate = SimpleNamespace(id=uuid.uuid4(), name="Alice", created_at="2026-01-01")
    log_activity = _patch_repos(monkeypatch, candidates=[candidate], continuity_hit=None)
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=candidate),
    )

    result = await bud_assignment.auto_assign_for_phase(
        fake_db, org_id, bud, BUDStatus.DEVELOPMENT
    )

    assert result == candidate.id
    completed = log_activity.await_args_list[-1].kwargs["metadata_"]
    assert completed["method"] == "smart_assignment"


# ── Chain-message bug (primary missing vs fallback at cap) ─────────────


@pytest.mark.asyncio
async def test_chain_message_attributes_primary_when_fallback_at_cap(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """Zero designers + PM at cap + nothing else → no_candidates names the primary.

    The screenshot bug: banner said "PM at capacity" while the user
    expected "no Designer". With the rewritten chain walker, fallback
    at-cap continues past, and the exhausted-chain outcome attributes
    the missing PRIMARY as the cause.
    """
    monkeypatch.setitem(bud_assignment.MAX_ACTIVE_BUDS_PER_ROLE, UserRole.PM, 1)
    pm = SimpleNamespace(id=uuid.uuid4(), name="OnlyPM", created_at="2026-01-01")

    async def list_active(_org_id: uuid.UUID, role: object) -> list[SimpleNamespace]:
        # DESIGN chain = (DESIGNER, PM, ORG_OWNER). Only PMs exist; they
        # are at cap. Designers and org_owners are empty.
        if role == UserRole.PM:
            return [pm]
        return []

    monkeypatch.setattr(
        bud_assignment,
        "UserRepository",
        MagicMock(
            return_value=MagicMock(list_active_with_role=AsyncMock(side_effect=list_active))
        ),
    )
    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(return_value={pm.id: 1})
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))
    timeline_repo = MagicMock()
    timeline_repo.latest_assignee_for_phase = AsyncMock(return_value=None)
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=False)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )
    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))

    bud = _make_bud()
    await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.DESIGN)

    log_activity.assert_awaited_once()
    kwargs = log_activity.await_args.kwargs
    assert kwargs["event_type"] == "skill_failed"
    meta = kwargs["metadata_"]
    # Critically: metadata attributes the missing PRIMARY (designer),
    # NOT the at-cap fallback (pm).
    assert meta["reason"] == "no_candidates"
    assert meta["role"] == "designer"
    assert meta["primary_role"] == "designer"
    assert "designer" in kwargs["message"].lower()
    assert "pm" not in kwargs["message"].lower()


@pytest.mark.asyncio
async def test_chain_never_falls_through_to_org_owner(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """ORG_OWNER is not in any chain — they never auto-receive a fallback BUD.

    Setup: zero designers, the only PM is at cap, an org_owner exists
    with zero active BUDs. Previously the chain walked PM→ORG_OWNER and
    silently assigned the owner. Now ORG_OWNER is absent from
    ``PHASE_ROLE_CHAIN``, so the walk ends at the empty fallbacks and
    surfaces "no_candidates" against the primary (designer).
    """
    monkeypatch.setitem(bud_assignment.MAX_ACTIVE_BUDS_PER_ROLE, UserRole.PM, 1)
    pm = SimpleNamespace(id=uuid.uuid4(), name="BusyPM", created_at="2026-01-01")
    owner = SimpleNamespace(id=uuid.uuid4(), name="Owner", created_at="2026-01-02")

    queried_roles: list[UserRole] = []

    async def list_active(_org_id: uuid.UUID, role: object) -> list[SimpleNamespace]:
        # PM exists (but at cap); ORG_OWNER exists (and would have been
        # the old fallback target). DESIGNER is empty.
        if isinstance(role, UserRole):
            queried_roles.append(role)
        if role == UserRole.PM:
            return [pm]
        if role == UserRole.ORG_OWNER:
            return [owner]
        return []

    monkeypatch.setattr(
        bud_assignment,
        "UserRepository",
        MagicMock(
            return_value=MagicMock(list_active_with_role=AsyncMock(side_effect=list_active))
        ),
    )

    async def loads(ids: list[uuid.UUID], _statuses: list[str]) -> dict[uuid.UUID, int]:
        return {i: (1 if i == pm.id else 0) for i in ids}

    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(side_effect=loads)
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))
    timeline_repo = MagicMock()
    timeline_repo.latest_assignee_for_phase = AsyncMock(return_value=None)
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=False)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )
    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))
    # Smart picker would assign owner if reached — but it must not be reached.
    smart = AsyncMock(side_effect=AssertionError("smart picker called with org_owner pool"))
    monkeypatch.setattr("app.services.smart_assignment.assign_best_for_role", smart)

    bud = _make_bud()
    result = await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.DESIGN)

    # Unassigned + warning attributed to the missing primary.
    assert result is None
    assert bud.assignee_id is None
    smart.assert_not_called()
    # Owner is NEVER seen by the walk because ORG_OWNER isn't in the chain.
    assert UserRole.ORG_OWNER not in queried_roles
    log_activity.assert_awaited_once()
    meta = log_activity.await_args.kwargs["metadata_"]
    assert meta["reason"] == "no_candidates"
    assert meta["primary_role"] == "designer"


@pytest.mark.asyncio
async def test_manual_assign_records_role_for_continuity_lookups(
    monkeypatch: pytest.MonkeyPatch,
    fake_db: MagicMock,
    org_id: uuid.UUID,
) -> None:
    """``assign_bud(...)`` writes ``detail.role`` so continuity matches manual events."""
    assignee_id = uuid.uuid4()
    assignee = SimpleNamespace(id=assignee_id, name="Manual", email="m@x")

    user_repo = MagicMock()
    user_repo.get_role = AsyncMock(return_value=UserRole.PM)
    monkeypatch.setattr(bud_assignment, "UserRepository", MagicMock(return_value=user_repo))
    record_event = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "record_event", record_event)

    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=assignee)
    bud = _make_bud()
    bud.status = BUDStatus.BUD

    await bud_assignment.assign_bud(
        db, org_id, bud, assignee_id, actor_id=None, actor_name="admin"
    )

    record_event.assert_awaited_once()
    detail = record_event.await_args.kwargs["detail"]
    assert detail["method"] == "manual"
    assert detail["role"] == "pm"
    assert detail["assignee_id"] == str(assignee_id)
    # ``phase`` must be stamped so continuity lookups on future re-entry
    # can match by phase rather than role-in-chain.
    assert detail["phase"] == BUDStatus.BUD.value


# ── Phase-scoped continuity (no cross-phase bleed via fallback roles) ──


@pytest.mark.asyncio
async def test_first_design_entry_does_not_carry_pm_from_bud_phase(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
) -> None:
    """A PM assigned during BUD must NOT win continuity on first DESIGN entry.

    Regression for the original bug: DESIGN's chain is ``(DESIGNER, PM)``
    so the old role-in-chain continuity matched the previous PM event
    and short-circuited the designer pool. Phase-scoped lookup must
    return ``None`` for the unseen DESIGN phase and let the chain walk
    pick a designer.
    """
    designer = SimpleNamespace(id=uuid.uuid4(), name="Dee", created_at="2026-01-01")

    async def list_active(_org_id: uuid.UUID, role: object) -> list[SimpleNamespace]:
        return [designer] if role == UserRole.DESIGNER else []

    monkeypatch.setattr(
        bud_assignment,
        "UserRepository",
        MagicMock(
            return_value=MagicMock(
                list_active_with_role=AsyncMock(side_effect=list_active),
                get_role=AsyncMock(return_value=None),
            )
        ),
    )
    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(return_value={designer.id: 0})
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))
    timeline_repo = MagicMock()
    # Phase-scoped query for "design" must return None even though the
    # underlying timeline holds a PM ``assigned`` event from the BUD phase.
    timeline_repo.latest_assignee_for_phase = AsyncMock(return_value=None)
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=False)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )
    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=designer),
    )

    fake_db = MagicMock(name="AsyncSession")
    fake_db.get = AsyncMock(return_value=None)
    bud = _make_bud()

    result = await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.DESIGN)

    # Designer (the primary) wins; PM never enters the picture.
    assert result == designer.id
    timeline_repo.latest_assignee_for_phase.assert_awaited_once_with(
        bud.id, BUDStatus.DESIGN.value
    )
    completed = log_activity.await_args_list[-1].kwargs["metadata_"]
    assert completed["role"] == "designer"
    assert completed.get("method") != "continuity"


@pytest.mark.asyncio
async def test_testing_picks_qa_even_when_developer_was_just_assigned(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
) -> None:
    """DEV → CODE_REVIEW → TESTING must pick a QA, not retain the developer.

    Regression for the second bug: TESTING's chain is ``(QA, DEVELOPER)``
    and CODE_REVIEW writes another ``assigned`` event with role=developer.
    The old role-in-chain lookup matched that developer event; the
    phase-scoped lookup returns None for the unseen TESTING phase and
    lets the chain walk pick a QA.
    """
    qa = SimpleNamespace(id=uuid.uuid4(), name="Quinn", created_at="2026-01-01")

    async def list_active(_org_id: uuid.UUID, role: object) -> list[SimpleNamespace]:
        return [qa] if role == UserRole.QA else []

    monkeypatch.setattr(
        bud_assignment,
        "UserRepository",
        MagicMock(
            return_value=MagicMock(
                list_active_with_role=AsyncMock(side_effect=list_active),
                get_role=AsyncMock(return_value=None),
            )
        ),
    )
    bud_repo = MagicMock()
    bud_repo.count_active_loads_for_assignees = AsyncMock(return_value={qa.id: 0})
    monkeypatch.setattr(bud_assignment, "BUDRepository", MagicMock(return_value=bud_repo))
    timeline_repo = MagicMock()
    timeline_repo.latest_assignee_for_phase = AsyncMock(return_value=None)
    timeline_repo.latest_user_unassign_after = AsyncMock(return_value=False)
    monkeypatch.setattr(
        bud_assignment, "BUDTimelineRepository", MagicMock(return_value=timeline_repo)
    )
    log_activity = AsyncMock(return_value=None)
    monkeypatch.setattr(bud_assignment, "log_agent_activity", log_activity)
    monkeypatch.setattr(bud_assignment, "record_event", AsyncMock(return_value=None))
    monkeypatch.setattr(
        "app.services.smart_assignment.assign_best_for_role",
        AsyncMock(return_value=qa),
    )

    fake_db = MagicMock(name="AsyncSession")
    fake_db.get = AsyncMock(return_value=None)
    bud = _make_bud()
    bud.assignee_id = uuid.uuid4()  # the developer carried from CODE_REVIEW

    result = await bud_assignment.auto_assign_for_phase(fake_db, org_id, bud, BUDStatus.TESTING)

    assert result == qa.id
    timeline_repo.latest_assignee_for_phase.assert_awaited_once_with(
        bud.id, BUDStatus.TESTING.value
    )
    completed = log_activity.await_args_list[-1].kwargs["metadata_"]
    assert completed["role"] == "qa"
    assert completed.get("method") != "continuity"


@pytest.mark.asyncio
async def test_same_phase_re_entry_still_uses_continuity(
    monkeypatch: pytest.MonkeyPatch,
    org_id: uuid.UUID,
) -> None:
    """Re-entering the SAME phase must still carry over the previous assignee.

    Guards against over-tightening: phase-scoped continuity must still
    fire when a BUD comes back to a phase it has already visited (e.g.
    DESIGN → DEV → back to DESIGN for rework).
    """
    designer = SimpleNamespace(id=uuid.uuid4(), name="Dee", created_at="2026-01-01")
    log_activity = _patch_continuity_world(
        monkeypatch,
        prev_user=designer,
        prev_role=UserRole.DESIGNER,
    )

    db = MagicMock(name="AsyncSession")
    db.get = AsyncMock(return_value=designer)
    bud = _make_bud()

    result = await bud_assignment.auto_assign_for_phase(db, org_id, bud, BUDStatus.DESIGN)

    assert result == designer.id
    completed = log_activity.await_args_list[-1].kwargs["metadata_"]
    assert completed["method"] == "continuity"
    assert completed["continuity_from_role"] == "designer"
