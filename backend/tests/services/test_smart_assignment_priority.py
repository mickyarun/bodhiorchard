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

"""Priority-weighted workload scoring.

The scorer must prefer candidates carrying lower-priority work. With the
new effective-load semantics (sum of ``BUD_PRIORITY_WEIGHTS`` over each
candidate's active BUDs), a developer holding four P3s ties with one
holding a single P0 — both have effective load 4. Adding a fifth P3
should tip the tie toward the P0-holder, since their effective load is
now lower in proportion.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.bud import BUDPriority
from app.services import smart_assignment
from app.services.smart_assignment import BUD_PRIORITY_WEIGHTS, score_candidates


def _user(name: str) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), name=name, email=f"{name.lower()}@example.com")


def _bud_without_impact() -> SimpleNamespace:
    """A BUD with no impacted_repos so the workload-only short-circuit fires.

    Isolates the priority-weighted workload term from skill + recency,
    which would otherwise drown out the load signal in this test.
    """
    return SimpleNamespace(
        id=uuid.uuid4(),
        impacted_repos=None,
        title="t",
        tech_spec_md=None,
    )


@pytest.fixture(autouse=True)
def _patch_skill_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    """No skill rows — forces the workload-only path inside score_candidates."""
    monkeypatch.setattr(
        smart_assignment,
        "SkillProfileRepository",
        MagicMock(return_value=MagicMock(list_for_users=AsyncMock(return_value=[]))),
    )


def test_priority_weights_are_p0_heaviest_p3_lightest() -> None:
    """Sanity check: the policy constants are ordered correctly."""
    assert BUD_PRIORITY_WEIGHTS[BUDPriority.P0] > BUD_PRIORITY_WEIGHTS[BUDPriority.P1]
    assert BUD_PRIORITY_WEIGHTS[BUDPriority.P1] > BUD_PRIORITY_WEIGHTS[BUDPriority.P2]
    assert BUD_PRIORITY_WEIGHTS[BUDPriority.P2] > BUD_PRIORITY_WEIGHTS[BUDPriority.P3]


@pytest.mark.asyncio
async def test_equal_effective_load_produces_equal_score() -> None:
    """Four P3s (load 4) and one P0 (load 4) score equally on workload."""
    alice = _user("Alice")  # four P3s — effective load 4
    bob = _user("Bob")  # one P0 — effective load 4
    weighted = {alice.id: 4, bob.id: 4}

    scored = await score_candidates(
        db=MagicMock(),
        org_id=uuid.uuid4(),
        bud=_bud_without_impact(),
        candidates=[alice, bob],
        load_map=weighted,
    )

    assert {u.id for u, _ in scored} == {alice.id, bob.id}
    a_score = next(s for u, s in scored if u.id == alice.id)
    b_score = next(s for u, s in scored if u.id == bob.id)
    assert a_score == b_score


@pytest.mark.asyncio
async def test_extra_p3_tips_tie_to_p0_holder() -> None:
    """Five P3s (load 5) vs one P0 (load 4) — the P0-holder wins."""
    alice = _user("Alice")  # five P3s — effective load 5
    bob = _user("Bob")  # one P0 — effective load 4
    weighted = {alice.id: 5, bob.id: 4}

    scored = await score_candidates(
        db=MagicMock(),
        org_id=uuid.uuid4(),
        bud=_bud_without_impact(),
        candidates=[alice, bob],
        load_map=weighted,
    )

    winner = scored[0][0]
    assert winner.id == bob.id


@pytest.mark.asyncio
async def test_zero_load_beats_any_loaded_candidate() -> None:
    """A candidate with no active work always wins workload-only scoring."""
    alice = _user("Alice")  # idle
    bob = _user("Bob")  # one P0 — weight 4
    weighted = {alice.id: 0, bob.id: 4}

    scored = await score_candidates(
        db=MagicMock(),
        org_id=uuid.uuid4(),
        bud=_bud_without_impact(),
        candidates=[alice, bob],
        load_map=weighted,
    )

    assert scored[0][0].id == alice.id


@pytest.mark.asyncio
async def test_priority_signal_decides_when_skill_and_recency_tie(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Full skill+workload path: equal skill + recency → priority breaks the tie.

    Regression guard: if a future change accidentally passed the
    count-based ``load_map`` to ``score_candidates`` instead of the
    weighted one, this test would still see equal scores (both
    candidates hold one BUD) and the priority-loaded candidate would no
    longer lose. With the correct wiring, Bob's P0 load (4) outweighs
    Alice's P3 load (1) and Alice wins.
    """
    alice = _user("Alice")
    bob = _user("Bob")

    bud = SimpleNamespace(
        id=uuid.uuid4(),
        impacted_repos=[{"repo_name": "core"}],
        title="t",
        tech_spec_md=None,
    )

    # Both candidates have identical skill rows for the impacted module —
    # skill + recency scores are equal, leaving workload as the only signal.
    same_touch = SimpleNamespace(
        module="core",
        skill_score=1.0,
        touch_count=10,
        last_touch=datetime.now(UTC),
    )
    skills = [
        SimpleNamespace(user_id=alice.id, **same_touch.__dict__),
        SimpleNamespace(user_id=bob.id, **same_touch.__dict__),
    ]
    monkeypatch.setattr(
        smart_assignment,
        "SkillProfileRepository",
        MagicMock(return_value=MagicMock(list_for_users=AsyncMock(return_value=skills))),
    )

    # Alice holds one P3 (weight 1); Bob holds one P0 (weight 4).
    weighted = {
        alice.id: BUD_PRIORITY_WEIGHTS[BUDPriority.P3],
        bob.id: BUD_PRIORITY_WEIGHTS[BUDPriority.P0],
    }

    scored = await score_candidates(
        db=MagicMock(),
        org_id=uuid.uuid4(),
        bud=bud,
        candidates=[alice, bob],
        load_map=weighted,
    )

    assert scored[0][0].id == alice.id, "candidate with lower weighted load must win"
