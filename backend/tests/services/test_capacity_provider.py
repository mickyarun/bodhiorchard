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

"""Tests for capacity_provider.

The DB query in ``get_role_loads`` is exercised by integration tests
elsewhere; these unit tests focus on the *math* — that the pure
``phase_capacity`` / ``capacity_by_phase`` queueing curve and chain
pooling are correct in isolation, without spinning up a session.
"""

from __future__ import annotations

from app.models.user import UserRole
from app.services.capacity_provider import RoleLoad, capacity_by_phase, phase_capacity
from app.services.estimation_engine import MIN_CAPACITY


def test_phase_capacity_uses_queueing_curve() -> None:
    """Capacity is the M/M/1 availability ratio pool/(pool+active), not
    the old subtractive 1-active/pool. Idle pool → 1.0; equal load →
    0.5; never crosses zero however overloaded."""
    loads = {UserRole.DEVELOPER: RoleLoad(pool=4, active=0)}
    assert phase_capacity(loads, "development") == 1.0

    loads = {UserRole.DEVELOPER: RoleLoad(pool=4, active=4)}
    assert phase_capacity(loads, "development") == 0.5

    # 1 dev, 9 active: old model → 1-9 = floored to MIN; queueing → 0.1
    # but still strictly positive and never negative.
    loads = {UserRole.DEVELOPER: RoleLoad(pool=1, active=9)}
    assert phase_capacity(loads, "development") == 0.1
    assert phase_capacity(loads, "development") > 0


def test_phase_capacity_pools_the_fallback_chain() -> None:
    """A lone specialist no longer bottoms out: design's chain is
    (DESIGNER, PM), so 1 designer + 2 PMs gives a pool of 3 against the
    designer's active load — not a pool of 1."""
    loads = {
        UserRole.DESIGNER: RoleLoad(pool=1, active=7),
        UserRole.PM: RoleLoad(pool=2, active=11),
    }
    # pool = 1 + 2 = 3, active = designer's 7 → 3/10 = 0.30
    assert phase_capacity(loads, "design") == 3 / 10

    # tech_arch chain (TECH_LEAD, DEVELOPER): a big dev pool rescues a
    # 2-person tech-lead pool that the old model floored at 0.1.
    loads = {
        UserRole.TECH_LEAD: RoleLoad(pool=2, active=12),
        UserRole.DEVELOPER: RoleLoad(pool=26, active=7),
    }
    # pool = 2 + 26 = 28, active = tech_lead's 12 → 28/40 = 0.70
    assert phase_capacity(loads, "tech_arch") == 28 / 40


def test_phase_capacity_unknown_phase_defaults_to_one() -> None:
    """Phases without a role chain must default to 1.0 (no adjustment).
    Defensive — keeps a renamed/added phase from silently breaking
    forecasting until PHASE_ROLE_CHAIN catches up."""
    assert phase_capacity({}, "made_up") == 1.0


def test_phase_capacity_empty_chain_pool_defaults_to_one() -> None:
    """When literally nobody staffs any role in the chain, capacity is
    1.0 (no inflation) — an unstaffable phase is the assignment banner's
    problem, not a number to silently stretch."""
    assert phase_capacity({}, "design") == 1.0
    assert phase_capacity({UserRole.DESIGNER: RoleLoad(0, 0)}, "design") == 1.0


def test_capacity_by_phase_projects_each_phase() -> None:
    """The per-phase projection the engine consumes is the contract — a
    bug here silently shifts the capacity divisor onto the wrong phase."""
    loads = {
        UserRole.DESIGNER: RoleLoad(pool=2, active=2),
        UserRole.PM: RoleLoad(pool=2, active=0),
        UserRole.DEVELOPER: RoleLoad(pool=4, active=0),
        UserRole.TECH_LEAD: RoleLoad(pool=0, active=0),
    }
    out = capacity_by_phase(loads, ["design", "development"])
    # design chain (DESIGNER, PM): pool 2+2=4, active 2 → 4/6
    assert out["design"] == 4 / 6
    # development chain (DEVELOPER, TECH_LEAD): pool 4+0=4, active 0 → 1.0
    assert out["development"] == 1.0


def test_min_capacity_is_floor_for_engine_divisor() -> None:
    """Sanity check: MIN_CAPACITY must be > 0, otherwise the engine's
    ``effort / divisor`` would be a divide-by-zero in the loaded-team
    case. Also < 1 because at >= 1 it would never bite. The queueing
    curve stays positive on its own, but the engine keeps this floor as
    a guard for pathological overload (active ≫ pool)."""
    assert 0 < MIN_CAPACITY < 1
