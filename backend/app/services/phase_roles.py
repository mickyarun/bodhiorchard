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

"""Static map from BUD lifecycle phase to the org role that owns it.

The smart-assignment agent picks an actual person at the start of each
phase, so per-person capacity is unknown when we estimate. Instead we
work at the role level: every phase is owned by exactly one
``UserRole``, and capacity for that phase is the role pool's current
availability (see ``capacity_provider``).

This map is the single source of truth — adding or renaming phases
should never need a parallel update elsewhere. Keep it sorted to match
``estimation_engine.PHASE_ORDER`` so reviewers can scan both at once.
"""

from app.models.user import UserRole

# Ordered fallback chain per phase. The PRIMARY role is the canonical
# owner; subsequent entries are degrade-by-adjacency fallbacks for orgs
# that haven't filled every working role (a small team often has
# developers but no dedicated tech lead, designer, or QA — the BUD
# should still flow, not stall with a red banner). When auto-assignment
# uses a fallback, the workflow banner shows "No active <primary> —
# assigned to <fallback>" so the user sees the substitution rather than
# a silent re-routing.
#
# ``ORG_OWNER`` is deliberately ABSENT from every chain. The owner is
# the admin, not a worker — silently auto-assigning their inbox would
# hide the workload problem (the org hasn't filled a real working role)
# rather than surfacing it. When the chain exhausts the BUD is left
# unassigned with an "all at capacity" / "no candidates" banner so the
# admin can fill the gap or reassign manually.
#
# Why "prod → DEVELOPER" first: there is no DEVOPS role in ``UserRole``
# today; the developer pool handles deploys until that's introduced.
# When a DEVOPS enum value lands, prepend it to the prod chain.
PHASE_ROLE_CHAIN: dict[str, tuple[UserRole, ...]] = {
    "bud": (UserRole.PM, UserRole.MANAGER),
    "design": (UserRole.DESIGNER, UserRole.PM),
    "tech_arch": (UserRole.TECH_LEAD, UserRole.DEVELOPER),
    "development": (UserRole.DEVELOPER, UserRole.TECH_LEAD),
    "code_review": (UserRole.DEVELOPER, UserRole.TECH_LEAD),
    "testing": (UserRole.QA, UserRole.DEVELOPER),
    "uat": (UserRole.PM, UserRole.MANAGER),
    "prod": (UserRole.DEVELOPER, UserRole.TECH_LEAD),
}

# Backwards-compatible single-role view. Consumers that only need the
# canonical role (capacity_provider, estimation helpers) read this; the
# auto-assigner reads ``PHASE_ROLE_CHAIN`` directly.
PHASE_ROLE_MAP: dict[str, UserRole] = {
    phase: chain[0] for phase, chain in PHASE_ROLE_CHAIN.items()
}


def get_role_for_phase(phase: str) -> UserRole | None:
    """Return the canonical role that owns this phase, or None for unknown phases.

    Returning None (rather than raising) lets callers in the estimation
    pipeline degrade gracefully — an unknown phase produces capacity 1.0
    (no adjustment) rather than crashing the whole forecast.
    """
    return PHASE_ROLE_MAP.get(phase)
