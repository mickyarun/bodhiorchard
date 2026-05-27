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
from app.services import yield_offer_service


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
    published: list[tuple[str, dict[str, object]]] = []
    monkeypatch.setattr(
        yield_offer_service, "publish", lambda topic, data: published.append((topic, data))
    )

    db = MagicMock()
    db.flush = AsyncMock()
    result = await yield_offer_service.reject_offer(db, uuid.uuid4(), offer.id, target_id)
    assert result.status == YieldOfferStatus.REJECTED
    assert published and published[0][1]["resolution"] == "rejected"
