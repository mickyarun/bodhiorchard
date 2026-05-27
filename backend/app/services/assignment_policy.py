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

"""Constants + helpers shared by the assignment services.

This module exists to break the import cycle between
``bud_assignment`` (the orchestrator) and ``smart_assignment`` (the
scorer). Both need to agree on terminal statuses, per-role capacity
caps, and priority weights — putting those here lets both depend on a
leaf module instead of each other, so neither needs inline imports
inside function bodies.
"""

from app.models.bud import BUDPriority, BUDStatus
from app.models.user import UserRole

# Statuses that don't count toward a user's active workload.
TERMINAL_BUD_STATUSES: frozenset[BUDStatus] = frozenset(
    {BUDStatus.CLOSED, BUDStatus.DISCARDED, BUDStatus.PROD}
)

# Per-role limit on concurrent active BUDs. A candidate with this many
# (or more) active BUDs is excluded — auto-assignment leaves the BUD
# unassigned with an ``all_at_capacity`` warning rather than overloading
# someone further. Tuned by role realities: PMs juggle many; devs work
# deeply on a few; designers + QA sit in between.
#
# ``ORG_OWNER`` is intentionally NOT a key — the owner isn't a working
# role in ``PHASE_ROLE_CHAIN`` either. They can still be assigned
# manually if needed.
MAX_ACTIVE_BUDS_PER_ROLE: dict[UserRole, int] = {
    UserRole.PM: 10,
    UserRole.MANAGER: 8,
    UserRole.DESIGNER: 5,
    UserRole.QA: 5,
    UserRole.TECH_LEAD: 4,
    UserRole.DEVELOPER: 3,
}
_DEFAULT_MAX_ACTIVE_BUDS = 3


def max_active_buds_for(role: UserRole) -> int:
    """Return the active-BUD cap for ``role``, falling back to the default."""
    return MAX_ACTIVE_BUDS_PER_ROLE.get(role, _DEFAULT_MAX_ACTIVE_BUDS)


# Per-priority effective-load weights. A candidate's "workload" for
# scoring is the sum of these over their active BUDs — not the raw
# count. Holding one P0 (weight 4) is equivalent to holding four P3s
# (4 * 1). Capacity caps stay count-based; only scoring uses these.
BUD_PRIORITY_WEIGHTS: dict[BUDPriority, int] = {
    BUDPriority.P0: 4,
    BUDPriority.P1: 3,
    BUDPriority.P2: 2,
    BUDPriority.P3: 1,
}
