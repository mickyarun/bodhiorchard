# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for capacity_provider.

The DB query in ``get_role_capacity`` is exercised by integration tests
elsewhere; these unit tests focus on the *math* — that the pure
``capacity_by_phase`` projection and the floor / fallback behaviour are
correct in isolation, without spinning up a session.
"""

from __future__ import annotations

from app.models.user import UserRole
from app.services.capacity_provider import capacity_by_phase
from app.services.estimation_engine import MIN_CAPACITY


def test_capacity_by_phase_maps_each_phase_through_role() -> None:
    """Per-role capacity must land on the correct per-phase slot via
    PHASE_ROLE_MAP. This is the contract the engine relies on — a bug
    here silently shifts the capacity divisor onto the wrong phase."""
    role_capacity = {
        UserRole.DESIGNER: 0.4,
        UserRole.DEVELOPER: 0.7,
        UserRole.QA: 1.0,
        UserRole.PM: 0.8,
        UserRole.TECH_LEAD: 0.6,
    }
    out = capacity_by_phase(
        role_capacity,
        ["design", "tech_arch", "development", "testing"],
    )
    assert out["design"] == 0.4
    assert out["tech_arch"] == 0.6
    assert out["development"] == 0.7
    assert out["testing"] == 1.0


def test_capacity_by_phase_unknown_phase_defaults_to_one() -> None:
    """Phases without a role mapping must default to 1.0 (no
    adjustment). Defensive — keeps a renamed/added phase from silently
    breaking forecasting until PHASE_ROLE_MAP catches up."""
    out = capacity_by_phase({UserRole.DEVELOPER: 0.5}, ["development", "made_up"])
    assert out["development"] == 0.5
    assert out["made_up"] == 1.0


def test_capacity_by_phase_missing_role_in_dict_defaults_to_one() -> None:
    """When the role exists in PHASE_ROLE_MAP but the supplied capacity
    dict lacks an entry for it (e.g. the org has no designers and the
    DB query never returned that role), the phase falls back to 1.0
    rather than KeyError."""
    out = capacity_by_phase({}, ["design", "development"])
    assert out["design"] == 1.0
    assert out["development"] == 1.0


def test_min_capacity_is_floor_for_engine_divisor() -> None:
    """Sanity check: MIN_CAPACITY must be > 0, otherwise the engine's
    ``effort / divisor`` would be a divide-by-zero in the loaded-team
    case. Also < 1 because at >= 1 it would never bite."""
    assert 0 < MIN_CAPACITY < 1
