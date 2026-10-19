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

"""Validation for an employee's list of reporting managers (pure, no I/O).

An employee may report to several people; any one of them can approve
their leave. The rules:

* every manager is an active member of the same org,
* nobody manages themself,
* no reporting cycles (A reports to B reports to A, at any depth),
* exactly one primary when there are managers — the first one listed if
  none is marked.
"""

import uuid
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


class ManagerValidationError(ValueError):
    """The requested manager list breaks one of the rules above."""


@dataclass(frozen=True)
class ManagerChoice:
    """One requested manager."""

    user_id: uuid.UUID
    is_primary: bool = False


def normalize_primary(choices: Sequence[ManagerChoice]) -> list[tuple[uuid.UUID, bool]]:
    """Dedupe and settle the primary flag; returns ``(user_id, is_primary)`` pairs."""
    seen: dict[uuid.UUID, bool] = {}
    for choice in choices:
        seen[choice.user_id] = seen.get(choice.user_id, False) or choice.is_primary
    primaries = [uid for uid, primary in seen.items() if primary]
    if len(primaries) > 1:
        raise ManagerValidationError("Mark only one manager as primary.")
    if not seen:
        return []
    primary = primaries[0] if primaries else next(iter(seen))
    return [(uid, uid == primary) for uid in seen]


def would_create_cycle(
    employee: uuid.UUID,
    managers: Iterable[uuid.UUID],
    edges: Iterable[tuple[uuid.UUID, uuid.UUID]],
) -> bool:
    """True if giving ``employee`` these managers closes a reporting loop.

    ``edges`` are existing ``(employee, manager)`` pairs. The employee's
    own current links are ignored since they are being replaced.
    """
    reports_to: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for who, manager in edges:
        if who != employee:
            reports_to[who].add(manager)
    stack = list(managers)
    visited: set[uuid.UUID] = set()
    while stack:
        current = stack.pop()
        if current == employee:
            return True
        if current in visited:
            continue
        visited.add(current)
        stack.extend(reports_to.get(current, ()))
    return False


def validate_managers(
    employee: uuid.UUID,
    choices: Sequence[ManagerChoice],
    *,
    active_members: set[uuid.UUID],
    edges: Iterable[tuple[uuid.UUID, uuid.UUID]],
    existing: set[uuid.UUID] | None = None,
) -> list[tuple[uuid.UUID, bool]]:
    """Check every rule and return the normalized ``(user_id, is_primary)`` list.

    ``existing`` are the employee's current managers. They may stay even if
    since deactivated, so HR can still change the primary or add someone
    without first removing a manager who left; new additions must be active.
    """
    pairs = normalize_primary(choices)
    ids = [uid for uid, _ in pairs]
    kept = existing or set()
    if employee in ids:
        raise ManagerValidationError("Someone can't be their own manager.")
    if any(uid not in active_members and uid not in kept for uid in ids):
        raise ManagerValidationError("Managers must be active members of this organization.")
    if would_create_cycle(employee, ids, edges):
        raise ManagerValidationError(
            "That would create a reporting loop: someone in this chain already reports to them."
        )
    return pairs


def has_cycle(edges: Iterable[tuple[uuid.UUID, uuid.UUID]]) -> bool:
    """True if the ``(employee, manager)`` graph contains any reporting loop."""
    reports_to: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for who, manager in edges:
        reports_to[who].add(manager)
    done: set[uuid.UUID] = set()
    for start in list(reports_to):
        path: set[uuid.UUID] = set()
        stack: list[tuple[uuid.UUID, bool]] = [(start, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                path.discard(node)
                done.add(node)
                continue
            if node in path:
                return True
            if node in done:
                continue
            path.add(node)
            stack.append((node, True))
            stack.extend((nxt, False) for nxt in reports_to.get(node, ()))
    return False
