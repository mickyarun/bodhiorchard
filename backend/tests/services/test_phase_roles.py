# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Tests for the phase → role static map.

These tests exist to catch the silent failure mode where someone adds a
new lifecycle phase to ``estimation_engine.PHASE_ORDER`` and forgets to
extend ``PHASE_ROLE_MAP`` — the engine would silently default that
phase's capacity to 1.0 and the forecast would be wrong without anyone
noticing. Keep them strict.
"""

from __future__ import annotations

from app.models.user import UserRole
from app.services.estimation_engine import PHASE_ORDER
from app.services.phase_roles import PHASE_ROLE_MAP, get_role_for_phase


def test_every_lifecycle_phase_has_a_role() -> None:
    """Adding a phase to PHASE_ORDER without updating PHASE_ROLE_MAP would
    mean capacity for that phase silently defaults to 1.0, hiding the
    accuracy regression. The two lists must move together."""
    missing = [p for p in PHASE_ORDER if p not in PHASE_ROLE_MAP]
    assert missing == [], f"phases without a role mapping: {missing}"


def test_unknown_phase_returns_none() -> None:
    """Unknown phases return None (capacity falls back to 1.0 in the
    engine) rather than raising — degrading gracefully matters more
    than failing loud here, because forecasts are advisory."""
    assert get_role_for_phase("not_a_real_phase") is None


def test_known_phase_returns_expected_role() -> None:
    assert get_role_for_phase("design") is UserRole.DESIGNER
    assert get_role_for_phase("development") is UserRole.DEVELOPER
    assert get_role_for_phase("testing") is UserRole.QA


def test_all_mapped_roles_are_valid_user_roles() -> None:
    """Guard against typos when the map is hand-edited — every value
    must be a real UserRole so capacity_provider can join against
    OrgToUser without missing rows."""
    for phase, role in PHASE_ROLE_MAP.items():
        assert isinstance(role, UserRole), f"{phase} is mapped to non-UserRole {role!r}"
