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

"""Yield-offer orchestration tests.

Verifies the create-pick-publish flow and the accept/reject guards.
The repo + bud repo are mocked; we're testing the picker logic and
the published event payloads, not SQL.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bud import BUDPriority
from app.models.yield_offer import YieldOfferStatus
from app.services import yield_offer_lock, yield_offer_service


def _bud(priority: BUDPriority, assignee_id: uuid.UUID | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        bud_number=42,
        title="t",
        priority=priority,
        assignee_id=assignee_id,
    )


def _user(name: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name=name)


@pytest.fixture(autouse=True)
def _stub_assignment_actions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default no-op assign/unassign so accept_offer doesn't hit the DB.

    Tests that assert on assign/unassign side effects override these.
    """
    monkeypatch.setattr(yield_offer_service, "assign_bud", AsyncMock(return_value=None))
    monkeypatch.setattr(yield_offer_service, "unassign_bud", AsyncMock(return_value=None))


@pytest.mark.asyncio
async def test_no_offer_when_no_candidate_holds_lower_priority(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All saturated candidates hold the same priority as the incoming — no offer."""
    incoming = _bud(BUDPriority.P1)
    alice = _user("Alice")
    alice_bud = _bud(BUDPriority.P1, assignee_id=alice.id)

    yield_repo = MagicMock()
    yield_repo.has_pending_for_incoming_bud = AsyncMock(return_value=False)
    monkeypatch.setattr(
        yield_offer_service,
        "YieldOfferRepository",
        MagicMock(return_value=yield_repo),
    )

    bud_repo = MagicMock()
    bud_repo.lowest_priority_active_for_assignee = AsyncMock(return_value=alice_bud)
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))

    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        yield_offer_service, "publish", lambda topic, data: published.append((topic, data))
    )

    offer = await yield_offer_service.maybe_raise_yield_offer(
        db=MagicMock(),
        org_id=uuid.uuid4(),
        incoming_bud=incoming,
        saturated_candidates=[alice],
    )
    assert offer is None
    assert published == []


@pytest.mark.asyncio
async def test_picks_widest_priority_gap_and_publishes_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """P0 incoming + Alice(P2) + Bob(P3) → Bob wins (widest gap)."""
    incoming = _bud(BUDPriority.P0)
    alice = _user("Alice")
    bob = _user("Bob")
    alice_bud = _bud(BUDPriority.P2, assignee_id=alice.id)
    bob_bud = _bud(BUDPriority.P3, assignee_id=bob.id)

    yield_repo = MagicMock()
    yield_repo.has_pending_for_incoming_bud = AsyncMock(return_value=False)

    async def _create(entity: object) -> object:
        return entity

    yield_repo.create = AsyncMock(side_effect=_create)
    monkeypatch.setattr(
        yield_offer_service,
        "YieldOfferRepository",
        MagicMock(return_value=yield_repo),
    )

    # Each candidate gets their lowest-priority active BUD from the repo.
    lowest_by_user = {alice.id: alice_bud, bob.id: bob_bud}

    async def _lowest(user_id: uuid.UUID, _statuses: list[str]) -> object:
        return lowest_by_user[user_id]

    bud_repo = MagicMock()
    bud_repo.lowest_priority_active_for_assignee = AsyncMock(side_effect=_lowest)
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))

    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        yield_offer_service, "publish", lambda topic, data: published.append((topic, data))
    )

    offer = await yield_offer_service.maybe_raise_yield_offer(
        db=MagicMock(),
        org_id=uuid.uuid4(),
        incoming_bud=incoming,
        saturated_candidates=[alice, bob],
    )
    assert offer is not None
    assert offer.target_user_id == bob.id
    assert offer.yieldable_bud_id == bob_bud.id
    assert offer.status == YieldOfferStatus.PENDING
    assert len(published) == 1
    topic, payload = published[0]
    assert topic == f"yield_offer:{bob.id}"
    assert payload["event"] == "created"
    assert payload["target_user_id"] == str(bob.id)


@pytest.mark.asyncio
async def test_idempotent_when_pending_offer_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An existing pending offer for the same BUD short-circuits, no duplicate."""
    incoming = _bud(BUDPriority.P0)
    alice = _user("Alice")

    yield_repo = MagicMock()
    yield_repo.has_pending_for_incoming_bud = AsyncMock(return_value=True)
    yield_repo.create = AsyncMock()
    monkeypatch.setattr(
        yield_offer_service,
        "YieldOfferRepository",
        MagicMock(return_value=yield_repo),
    )
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        yield_offer_service, "publish", lambda topic, data: published.append((topic, data))
    )

    offer = await yield_offer_service.maybe_raise_yield_offer(
        db=MagicMock(),
        org_id=uuid.uuid4(),
        incoming_bud=incoming,
        saturated_candidates=[alice],
    )
    assert offer is None
    yield_repo.create.assert_not_called()
    assert published == []


@pytest.mark.asyncio
async def test_accept_routes_through_assign_unassign_with_correct_method(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept must route mutations through assign_bud / unassign_bud.

    Direct ``assignee_id =`` would skip the timeline events, continuity
    lookups, and DEVELOPMENT-phase TODO cascade — the whole point of
    the extraction. Assert the helpers are called with the right method
    (``yield_offer_accepted``) / reason (``yielded``).
    """
    target_id = uuid.uuid4()
    incoming = _bud(BUDPriority.P0)
    yieldable = _bud(BUDPriority.P3, assignee_id=target_id)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=incoming.id,
        yieldable_bud_id=yieldable.id,
        status=YieldOfferStatus.PENDING,
    )

    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service,
        "YieldOfferRepository",
        MagicMock(return_value=yield_repo),
    )

    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(side_effect=[yieldable, incoming])
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))

    assign_mock = AsyncMock(return_value=None)
    unassign_mock = AsyncMock(return_value=None)
    monkeypatch.setattr(yield_offer_service, "assign_bud", assign_mock)
    monkeypatch.setattr(yield_offer_service, "unassign_bud", unassign_mock)
    # Unrelated to this assertion; stubbed so the close guard no-ops.
    _stub_parked(monkeypatch, None)

    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        yield_offer_service, "publish", lambda topic, data: published.append((topic, data))
    )

    db = MagicMock()
    db.flush = AsyncMock()

    result = await yield_offer_service.accept_offer(
        db, uuid.uuid4(), offer.id, target_id, "Acting User"
    )
    assert result.status == YieldOfferStatus.ACCEPTED
    unassign_mock.assert_awaited_once()
    _, unassign_kwargs = unassign_mock.await_args
    assert unassign_kwargs["reason"] == "yielded"
    assign_mock.assert_awaited_once()
    _, assign_kwargs = assign_mock.await_args
    assert assign_kwargs["method"] == "yield_offer_accepted"
    assert published and published[0][1]["resolution"] == "accepted"


@pytest.mark.asyncio
async def test_accept_rejects_wrong_user(monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the targeted user can accept."""
    target_id = uuid.uuid4()
    intruder_id = uuid.uuid4()
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=uuid.uuid4(),
        yieldable_bud_id=uuid.uuid4(),
        status=YieldOfferStatus.PENDING,
    )

    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service,
        "YieldOfferRepository",
        MagicMock(return_value=yield_repo),
    )

    with pytest.raises(ValueError, match="not addressed to this user"):
        await yield_offer_service.accept_offer(
            MagicMock(), uuid.uuid4(), offer.id, intruder_id, "Intruder"
        )


@pytest.mark.asyncio
async def test_reject_flips_status_and_publishes(monkeypatch: pytest.MonkeyPatch) -> None:
    target_id = uuid.uuid4()
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=uuid.uuid4(),
        yieldable_bud_id=uuid.uuid4(),
        status=YieldOfferStatus.PENDING,
    )

    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service,
        "YieldOfferRepository",
        MagicMock(return_value=yield_repo),
    )
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(return_value=_bud(BUDPriority.P0))
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    _stub_parked(monkeypatch, None)
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        yield_offer_service, "publish", lambda topic, data: published.append((topic, data))
    )

    db = MagicMock()
    db.flush = AsyncMock()
    result = await yield_offer_service.reject_offer(db, uuid.uuid4(), offer.id, target_id)
    assert result.status == YieldOfferStatus.REJECTED
    assert published and published[0][1]["resolution"] == "rejected"


# --- phase-assigner unlock -------------------------------------------------
#
# Raising a yield offer parks ``phase_assigner`` on a terminal-less
# ``skill_invoked``, which ``get_active_phase_worker`` reads as "an agent
# is running" and the BUD page turns into ``agentLocked`` — the entire
# status menu goes dead. Every path that resolves an offer therefore has
# to emit a terminal event. Before this was wired, the only thing that
# ever cleared it was the startup reconciler, so a long-lived deployment
# accumulated permanently frozen BUDs.


def _capture_activity(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, object]]:
    calls: list[dict[str, object]] = []

    async def _fake(_db: object, **kwargs: object) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(yield_offer_lock, "log_agent_activity", _fake)
    return calls


def _stub_parked(monkeypatch: pytest.MonkeyPatch, offer_id: uuid.UUID | None) -> None:
    """Stand up the parked ``skill_invoked`` the close guard looks for.

    ``offer_id=None`` simulates a BUD whose phase assigner was already
    closed (e.g. by the startup reconciler) — the close must then no-op
    rather than stamp a stale terminal event on an unrelated run.
    """
    parked = (
        None
        if offer_id is None
        else SimpleNamespace(
            metadata_={"offer_id": str(offer_id), "reason": "yield_offer_pending"}
        )
    )
    activity_repo = MagicMock()
    activity_repo.get_active_phase_worker = AsyncMock(return_value=parked)
    monkeypatch.setattr(
        yield_offer_lock,
        "AgentActivityLogRepository",
        MagicMock(return_value=activity_repo),
    )


def _phase_assigner_calls(calls: list[dict[str, object]]) -> list[dict[str, object]]:
    return [c for c in calls if c.get("skill_slug") == "phase_assigner"]


@pytest.mark.asyncio
async def test_reject_closes_phase_assigner(monkeypatch: pytest.MonkeyPatch) -> None:
    target_id = uuid.uuid4()
    incoming = _bud(BUDPriority.P0)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=incoming.id,
        yieldable_bud_id=uuid.uuid4(),
        status=YieldOfferStatus.PENDING,
    )
    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(return_value=incoming)
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    monkeypatch.setattr(yield_offer_service, "publish", lambda topic, data: None)
    _stub_parked(monkeypatch, offer.id)
    calls = _capture_activity(monkeypatch)

    db = MagicMock()
    db.flush = AsyncMock()
    await yield_offer_service.reject_offer(db, uuid.uuid4(), offer.id, target_id)

    closed = _phase_assigner_calls(calls)
    assert len(closed) == 1
    assert closed[0]["event_type"] == "skill_failed"
    assert closed[0]["bud_id"] == incoming.id
    assert closed[0]["metadata_"] == {"reason": "yield_offer_rejected"}


@pytest.mark.asyncio
async def test_accept_closes_phase_assigner(monkeypatch: pytest.MonkeyPatch) -> None:
    target_id = uuid.uuid4()
    incoming = _bud(BUDPriority.P0)
    yieldable = _bud(BUDPriority.P3, assignee_id=target_id)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=incoming.id,
        yieldable_bud_id=yieldable.id,
        status=YieldOfferStatus.PENDING,
    )
    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(side_effect=[yieldable, incoming])
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    monkeypatch.setattr(yield_offer_service, "assign_bud", AsyncMock(return_value=None))
    monkeypatch.setattr(yield_offer_service, "unassign_bud", AsyncMock(return_value=None))
    monkeypatch.setattr(yield_offer_service, "publish", lambda topic, data: None)
    _stub_parked(monkeypatch, offer.id)
    calls = _capture_activity(monkeypatch)

    db = MagicMock()
    db.flush = AsyncMock()
    await yield_offer_service.accept_offer(db, uuid.uuid4(), offer.id, target_id, "Dev")

    closed = _phase_assigner_calls(calls)
    assert len(closed) == 1
    # Accept actually assigns the BUD, so the worker completed rather than failed.
    assert closed[0]["event_type"] == "skill_completed"
    assert closed[0]["metadata_"] == {"reason": "yield_offer_accepted"}


@pytest.mark.asyncio
async def test_ttl_expiry_closes_phase_assigner_for_each_bud(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The TTL sweep is where the prod lock came from — 10 of 11 stuck BUDs
    had an offer that had already expired, so the unlock has to fire per
    expired row, not only on accept/reject."""
    org_id = uuid.uuid4()
    offer_a, offer_b = uuid.uuid4(), uuid.uuid4()
    bud_a, bud_b = uuid.uuid4(), uuid.uuid4()

    yield_repo = MagicMock()
    yield_repo.expire_overdue = AsyncMock(return_value=[(offer_a, bud_a), (offer_b, bud_b)])
    yield_repo.list_pending_for_user = AsyncMock(return_value=[])
    monkeypatch.setattr(
        yield_offer_service, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_minimal_info_by_ids = AsyncMock(
        return_value={
            bud_a: {"number": 7, "title": "A"},
            bud_b: {"number": 8, "title": "B"},
        }
    )
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    # Each BUD is still parked on its own offer, so both close.
    activity_repo = MagicMock()
    activity_repo.get_active_phase_worker = AsyncMock(
        side_effect=[
            SimpleNamespace(metadata_={"offer_id": str(offer_a)}),
            SimpleNamespace(metadata_={"offer_id": str(offer_b)}),
        ]
    )
    monkeypatch.setattr(
        yield_offer_lock,
        "AgentActivityLogRepository",
        MagicMock(return_value=activity_repo),
    )
    calls = _capture_activity(monkeypatch)

    await yield_offer_service.list_pending_with_expiry(MagicMock(), org_id, uuid.uuid4())

    closed = _phase_assigner_calls(calls)
    assert [c["bud_id"] for c in closed] == [bud_a, bud_b]
    assert {c["event_type"] for c in closed} == {"skill_failed"}
    assert {c["metadata_"]["reason"] for c in closed} == {"yield_offer_expired"}  # type: ignore[index]
    assert [c["bud_number"] for c in closed] == [7, 8]


@pytest.mark.asyncio
async def test_ttl_expiry_emits_nothing_when_no_offer_expired(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The common case: bell-open with nothing overdue must stay silent."""
    yield_repo = MagicMock()
    yield_repo.expire_overdue = AsyncMock(return_value=[])
    yield_repo.list_pending_for_org = AsyncMock(return_value=[])
    monkeypatch.setattr(
        yield_offer_service, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_minimal_info_by_ids = AsyncMock(return_value={})
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    calls = _capture_activity(monkeypatch)

    await yield_offer_service.list_org_pending_with_expiry(MagicMock(), uuid.uuid4())

    assert _phase_assigner_calls(calls) == []
    bud_repo.get_minimal_info_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_reject_skips_close_when_phase_assigner_already_moved_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A restart-time reconcile can close the loop before the offer resolves.

    The BUD then carries on into other phases. Stamping a terminal event
    anyway would either raise a stale "assignment skipped" banner on a BUD
    that has moved on, or clobber a genuinely in-flight phase worker.
    """
    target_id = uuid.uuid4()
    incoming = _bud(BUDPriority.P0)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=incoming.id,
        yieldable_bud_id=uuid.uuid4(),
        status=YieldOfferStatus.PENDING,
    )
    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(return_value=incoming)
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    monkeypatch.setattr(yield_offer_service, "publish", lambda topic, data: None)
    _stub_parked(monkeypatch, None)  # nothing parked — already reconciled
    calls = _capture_activity(monkeypatch)

    db = MagicMock()
    db.flush = AsyncMock()
    result = await yield_offer_service.reject_offer(db, uuid.uuid4(), offer.id, target_id)

    # The reject itself still lands; only the redundant unlock is skipped.
    assert result.status == YieldOfferStatus.REJECTED
    assert _phase_assigner_calls(calls) == []


@pytest.mark.asyncio
async def test_close_skips_when_parked_event_belongs_to_another_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two offers can exist for one BUD; only the parked one may close it."""
    target_id = uuid.uuid4()
    incoming = _bud(BUDPriority.P0)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=incoming.id,
        yieldable_bud_id=uuid.uuid4(),
        status=YieldOfferStatus.PENDING,
    )
    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(return_value=incoming)
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    monkeypatch.setattr(yield_offer_service, "publish", lambda topic, data: None)
    _stub_parked(monkeypatch, uuid.uuid4())  # a different offer holds the lock
    calls = _capture_activity(monkeypatch)

    db = MagicMock()
    db.flush = AsyncMock()
    await yield_offer_service.reject_offer(db, uuid.uuid4(), offer.id, target_id)

    assert _phase_assigner_calls(calls) == []


@pytest.mark.asyncio
async def test_close_failure_propagates_instead_of_being_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed activity write must surface, not be logged and ignored.

    ``log_agent_activity`` flushes on the caller's session, so a swallowed
    failure leaves the transaction needing rollback — the request would
    then die at commit with an opaque PendingRollbackError, and the TTL
    sweep would fail identically on every retry because it could never
    commit. Propagating keeps the unlock atomic with the reject.
    """
    target_id = uuid.uuid4()
    incoming = _bud(BUDPriority.P0)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=incoming.id,
        yieldable_bud_id=uuid.uuid4(),
        status=YieldOfferStatus.PENDING,
    )
    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(return_value=incoming)
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    monkeypatch.setattr(yield_offer_service, "publish", lambda topic, data: None)
    _stub_parked(monkeypatch, offer.id)
    monkeypatch.setattr(
        yield_offer_lock,
        "log_agent_activity",
        AsyncMock(side_effect=RuntimeError("activity write failed")),
    )

    db = MagicMock()
    db.flush = AsyncMock()
    with pytest.raises(RuntimeError, match="activity write failed"):
        await yield_offer_service.reject_offer(db, uuid.uuid4(), offer.id, target_id)


# --- superseding an offer whose BUD got assigned elsewhere ------------------
#
# An offer only exists because the incoming BUD had nobody. Assigning it by
# any other route answers that question, so leaving the offer pending would
# both keep nagging the target and hold the phase-assigner lock (disabling
# the BUD's whole status menu) until the 24h TTL or the next restart.


@pytest.mark.asyncio
async def test_assigning_the_incoming_bud_supersedes_its_pending_offer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    org_id, bud_id, offer_id = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    target_id = uuid.uuid4()

    yield_repo = MagicMock()
    yield_repo.supersede_pending_for_incoming_bud = AsyncMock(return_value=[(offer_id, target_id)])
    monkeypatch.setattr(
        yield_offer_lock, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_minimal_info_by_ids = AsyncMock(
        return_value={bud_id: {"number": 12, "title": "T"}}
    )
    monkeypatch.setattr(yield_offer_lock, "BUDRepository", MagicMock(return_value=bud_repo))
    _stub_parked(monkeypatch, offer_id)
    calls = _capture_activity(monkeypatch)
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        yield_offer_lock, "publish", lambda topic, data: published.append((topic, data))
    )

    await yield_offer_lock.supersede_offers_for_assigned_bud(MagicMock(), org_id, bud_id)

    yield_repo.supersede_pending_for_incoming_bud.assert_awaited_once_with(bud_id)
    closed = _phase_assigner_calls(calls)
    assert len(closed) == 1
    assert closed[0]["event_type"] == "skill_failed"
    assert closed[0]["metadata_"] == {"reason": "yield_offer_superseded"}
    assert closed[0]["bud_number"] == 12
    # Somebody else's request resolved this offer, so the target's board
    # notice only drops the row if we publish — otherwise they click
    # Accept and hit the pending-status guard.
    assert published == [
        (
            f"yield_offer:{target_id}",
            {
                "event": "resolved",
                "offer_id": str(offer_id),
                "org_id": str(org_id),
                "target_user_id": str(target_id),
                "resolution": "superseded",
            },
        )
    ]


@pytest.mark.asyncio
async def test_assignment_with_no_pending_offer_touches_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The overwhelmingly common path: assignment must not pay for a BUD lookup."""
    yield_repo = MagicMock()
    yield_repo.supersede_pending_for_incoming_bud = AsyncMock(return_value=[])
    monkeypatch.setattr(
        yield_offer_lock, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_minimal_info_by_ids = AsyncMock(return_value={})
    monkeypatch.setattr(yield_offer_lock, "BUDRepository", MagicMock(return_value=bud_repo))
    published: list[object] = []
    monkeypatch.setattr(
        yield_offer_lock, "publish", lambda topic, data: published.append((topic, data))
    )
    calls = _capture_activity(monkeypatch)

    await yield_offer_lock.supersede_offers_for_assigned_bud(
        MagicMock(), uuid.uuid4(), uuid.uuid4()
    )

    assert published == []

    assert _phase_assigner_calls(calls) == []
    bud_repo.get_minimal_info_by_ids.assert_not_awaited()


@pytest.mark.asyncio
async def test_accept_settles_its_own_offer_before_assigning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Accept must not supersede itself.

    ``assign_bud`` supersedes every offer still pending for the BUD it
    assigns. If accept flipped its own status afterwards, its row would be
    caught by that sweep and emit ``yield_offer_superseded`` instead of
    ``yield_offer_accepted``. Pinning the ordering keeps the audit honest.
    """
    target_id = uuid.uuid4()
    incoming = _bud(BUDPriority.P0)
    yieldable = _bud(BUDPriority.P3, assignee_id=target_id)
    offer = SimpleNamespace(
        id=uuid.uuid4(),
        target_user_id=target_id,
        incoming_bud_id=incoming.id,
        yieldable_bud_id=yieldable.id,
        status=YieldOfferStatus.PENDING,
    )
    yield_repo = MagicMock()
    yield_repo.get_by_id = AsyncMock(return_value=offer)
    monkeypatch.setattr(
        yield_offer_service, "YieldOfferRepository", MagicMock(return_value=yield_repo)
    )
    bud_repo = MagicMock()
    bud_repo.get_by_id = AsyncMock(side_effect=[yieldable, incoming])
    monkeypatch.setattr(yield_offer_service, "BUDRepository", MagicMock(return_value=bud_repo))
    monkeypatch.setattr(yield_offer_service, "unassign_bud", AsyncMock(return_value=None))
    monkeypatch.setattr(yield_offer_service, "publish", lambda topic, data: None)
    _stub_parked(monkeypatch, offer.id)
    _capture_activity(monkeypatch)

    status_when_assigned: list[YieldOfferStatus] = []

    async def _assign(*_a: object, **_k: object) -> None:
        status_when_assigned.append(offer.status)

    monkeypatch.setattr(yield_offer_service, "assign_bud", _assign)

    db = MagicMock()
    db.flush = AsyncMock()
    await yield_offer_service.accept_offer(db, uuid.uuid4(), offer.id, target_id, "Dev")

    # Already terminal by the time assign_bud runs, so the sweep skips it.
    assert status_when_assigned == [YieldOfferStatus.ACCEPTED]


# --- a pending offer must not lock the BUD ---------------------------------
#
# Both a running phase worker and an offer waiting on a person show up as a
# trailing ``skill_invoked``. Only the first should set ``agentLocked``:
# nothing is executing while an offer is open, and who ends up owning the
# BUD has no bearing on whether it can change phase. Conflating them froze
# the status menu for the offer's entire 24h life.


def test_parked_yield_offer_is_not_a_running_worker() -> None:
    parked = SimpleNamespace(
        skill_slug="phase_assigner",
        metadata_={"reason": "yield_offer_pending", "offer_id": str(uuid.uuid4())},
    )
    assert yield_offer_lock.is_awaiting_human_decision(parked) is True


def test_genuine_phase_worker_still_locks() -> None:
    running = SimpleNamespace(skill_slug="pert_estimator", metadata_={"role": "developer"})
    assert yield_offer_lock.is_awaiting_human_decision(running) is False


def test_worker_with_no_metadata_still_locks() -> None:
    """Most invoked events carry no metadata; they must keep locking."""
    assert (
        yield_offer_lock.is_awaiting_human_decision(
            SimpleNamespace(skill_slug="phase_assigner", metadata_=None)
        )
        is False
    )


def test_no_active_worker_is_not_awaiting() -> None:
    assert yield_offer_lock.is_awaiting_human_decision(None) is False
