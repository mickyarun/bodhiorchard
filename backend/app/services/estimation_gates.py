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

"""Turnaround model for review / sign-off gate phases.

Gate phases (``bud``, ``uat``, ``code_review`` — see ``phase_roles.PHASE_KIND``)
are not hands-on-keyboard work; they are *review latency*: how long until a
reviewer picks the BUD up and signs off. That latency is bounded and largely
independent of the effort-days an LLM might estimate, so running it through
``effort ÷ capacity`` over-stretches it — a PM at 0.21 capacity turned a 4-day
UAT estimate into ~20 wall-clock days.

Instead the estimator gives each gate a small **turnaround budget**:

    turnaround = BASE + PENALTY_PER_BACKLOG · reviewer_backlog   (capped at CAP)

``reviewer_backlog`` is how many BUDs sit ahead in that reviewer role's queue
(the primary role's active count), so a swamped reviewer is still slower — but
never a month. The orchestrator turns that single number into a narrow PERT
triple via :func:`gate_pert` and feeds it to the Monte Carlo engine with a
capacity divisor of 1.0, so the engine stays a generic math kernel with no
knowledge of gate semantics.
"""

from __future__ import annotations

import structlog

from app.models.user import UserRole
from app.services.capacity_provider import RoleLoad
from app.services.estimation_engine import PERTEstimate
from app.services.phase_roles import PHASE_ROLE_CHAIN

logger = structlog.get_logger(__name__)

# Business-day turnaround for an idle reviewer: pick it up + sign off.
GATE_BASE_TURNAROUND_DAYS = 1.0
# Added latency per BUD already queued on the reviewer role. A loaded
# reviewer is slower to get to this one.
GATE_PENALTY_DAYS_PER_BACKLOG = 0.5
# Hard ceiling — a gate never costs more than this however swamped the
# reviewer, because a sign-off is not continuous person-days of work.
GATE_TURNAROUND_CAP_DAYS = 4.0

# Spread used to turn a single turnaround estimate into a PERT triple, so
# the Monte Carlo still produces percentiles + a variance for the project
# buffer. Narrow (review latency is fairly predictable) and centred on the
# turnaround as the most-likely value.
GATE_SPREAD_OPTIMISTIC = 0.6
GATE_SPREAD_PESSIMISTIC = 1.5


def gate_turnaround_days(role_loads: dict[UserRole, RoleLoad], phase: str) -> float:
    """Capped review-turnaround for one gate phase, in business days.

    ``reviewer_backlog`` is the primary owning role's active in-flight count
    (BUDs ahead in that reviewer's queue). An unknown phase or one whose role
    chain is empty falls back to the base turnaround — never raises, never
    inflates.
    """
    chain = PHASE_ROLE_CHAIN.get(phase)
    if not chain:
        # A phase only reaches here if ``is_gate_phase`` returned True, i.e.
        # it is listed in ``PHASE_KIND`` as a gate — yet it has no owning
        # role chain. That means the two maps have drifted. Mirror the warn
        # that ``capacity_provider.phase_capacity`` emits for its empty-pool
        # case so the misconfiguration is observable, not a silent 1-day floor.
        logger.warning(
            "gate_phase_missing_role_chain",
            phase=phase,
            action=(
                "defaulting to base turnaround; PHASE_KIND lists this as a gate "
                "but PHASE_ROLE_CHAIN has no owning role — the maps have drifted"
            ),
        )
        return GATE_BASE_TURNAROUND_DAYS
    reviewer_backlog = role_loads.get(chain[0], RoleLoad(0, 0)).active
    turnaround = GATE_BASE_TURNAROUND_DAYS + GATE_PENALTY_DAYS_PER_BACKLOG * reviewer_backlog
    return min(GATE_TURNAROUND_CAP_DAYS, turnaround)


def gate_pert(turnaround_days: float) -> PERTEstimate:
    """Build a narrow PERT triple centred on a gate's turnaround estimate."""
    return PERTEstimate(
        optimistic=round(turnaround_days * GATE_SPREAD_OPTIMISTIC, 2),
        most_likely=round(turnaround_days, 2),
        pessimistic=round(turnaround_days * GATE_SPREAD_PESSIMISTIC, 2),
    )
