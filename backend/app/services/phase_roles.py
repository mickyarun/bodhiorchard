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

# Why "prod → DEVELOPER": there is no DEVOPS role in ``UserRole`` today;
# the developer pool handles deploys until that's introduced. When a
# DEVOPS enum value lands, change this single line.
PHASE_ROLE_MAP: dict[str, UserRole] = {
    "bud": UserRole.PM,
    "design": UserRole.DESIGNER,
    "tech_arch": UserRole.TECH_LEAD,
    "development": UserRole.DEVELOPER,
    "code_review": UserRole.DEVELOPER,
    "testing": UserRole.QA,
    "uat": UserRole.PM,
    "prod": UserRole.DEVELOPER,
}


def get_role_for_phase(phase: str) -> UserRole | None:
    """Return the role that owns this phase, or None for unknown phases.

    Returning None (rather than raising) lets callers in the estimation
    pipeline degrade gracefully — an unknown phase produces capacity 1.0
    (no adjustment) rather than crashing the whole forecast.
    """
    return PHASE_ROLE_MAP.get(phase)
