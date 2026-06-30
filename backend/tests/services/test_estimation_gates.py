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

"""Tests for the review-gate turnaround model (pure functions, no session)."""

from __future__ import annotations

from app.models.user import UserRole
from app.services.capacity_provider import RoleLoad
from app.services.estimation_gates import (
    GATE_BASE_TURNAROUND_DAYS,
    GATE_TURNAROUND_CAP_DAYS,
    gate_pert,
    gate_turnaround_days,
)
from app.services.phase_roles import is_gate_phase


def test_idle_reviewer_gets_base_turnaround() -> None:
    """No BUDs ahead in the reviewer queue → the base turnaround, nothing more."""
    loads = {UserRole.PM: RoleLoad(pool=2, active=0)}
    assert gate_turnaround_days(loads, "uat") == GATE_BASE_TURNAROUND_DAYS


def test_backlog_adds_bounded_penalty() -> None:
    """Each queued BUD adds latency — a loaded reviewer is slower, linearly."""
    loads = {UserRole.PM: RoleLoad(pool=2, active=4)}
    # base 1.0 + 0.5 * 4 = 3.0
    assert gate_turnaround_days(loads, "uat") == 3.0


def test_turnaround_is_capped() -> None:
    """However swamped the reviewer, a gate never exceeds the cap — a sign-off
    is not continuous person-days. This is the property that kills the
    ~20-day-UAT pathology."""
    loads = {UserRole.PM: RoleLoad(pool=1, active=100)}
    assert gate_turnaround_days(loads, "uat") == GATE_TURNAROUND_CAP_DAYS


def test_code_review_keys_off_developer_backlog() -> None:
    """code_review is a gate owned by the developer pool — its turnaround
    scales with the developer queue, not the PM queue."""
    loads = {UserRole.DEVELOPER: RoleLoad(pool=26, active=2)}
    # base 1.0 + 0.5 * 2 = 2.0
    assert gate_turnaround_days(loads, "code_review") == 2.0


def test_unknown_phase_falls_back_to_base() -> None:
    """A phase with no role chain returns the base turnaround (never raises,
    never inflates) — the drift is logged, the number stays safe."""
    assert gate_turnaround_days({}, "made_up") == GATE_BASE_TURNAROUND_DAYS


def test_missing_role_in_loads_defaults_to_zero_backlog() -> None:
    """A gate role absent from the loads dict reads as zero backlog, not a
    KeyError — the positional RoleLoad(0, 0) default matches (pool, active)."""
    assert gate_turnaround_days({}, "uat") == GATE_BASE_TURNAROUND_DAYS


def test_gate_pert_is_narrow_and_centred_with_positive_spread() -> None:
    """The PERT triple centres on the turnaround and keeps a positive spread
    so the Monte Carlo still yields percentiles and a buffer variance."""
    est = gate_pert(2.0)
    assert est.most_likely == 2.0
    assert est.optimistic == 1.2  # 2.0 * 0.6
    assert est.pessimistic == 3.0  # 2.0 * 1.5
    assert est.optimistic < est.most_likely < est.pessimistic


def test_phase_kind_classification() -> None:
    """The three review/sign-off phases are gates; hands-on phases are not."""
    assert is_gate_phase("bud")
    assert is_gate_phase("uat")
    assert is_gate_phase("code_review")
    for build_phase in ("design", "tech_arch", "development", "testing", "prod"):
        assert not is_gate_phase(build_phase)
    # Unknown phases default to build (safe — keeps effort ÷ capacity).
    assert not is_gate_phase("made_up")
