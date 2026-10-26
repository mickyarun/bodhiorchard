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

"""Which existing leave types to link into the library, decided without guessing.

Types with the same name on different policies ("Sick leave" and "Sick
Leave", ignoring case and spacing) become one library entry. The entry
takes the first policy's values (oldest policy first); a policy whose quota
differs keeps it as its own, and every other difference is listed for the
owner to confirm before anything is applied. A name that already has a
library entry links to it. Pure: the caller loads rows and applies.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from app.models.leave_policy import LeavePolicy
from app.models.leave_type import LeaveType
from app.models.leave_type_template import LeaveTypeTemplate
from app.services.leave import config_audit
from app.services.leave.type_library import RULE_FIELDS


def name_key(name: str) -> str:
    """ "Sick  Leave" and "sick leave" are the same type."""
    return " ".join(name.split()).casefold()


@dataclass
class LinkMember:
    """One policy's type joining an entry, and what linking would change on it."""

    leave_type: LeaveType
    policy_name: str
    # Read when planned: the row itself is expired once a dry run rolls back.
    type_name: str
    quota: Decimal | None
    own_quota: bool
    # {field: [this policy's value, the library's]} for every rule but the quota.
    differences: dict[str, list[Any]]


@dataclass
class LinkGroup:
    """One library entry (new or existing) and the types that would follow it."""

    name: str
    # The values the entry has (existing) or would be created with (new).
    rules: dict[str, Any]
    existing: LeaveTypeTemplate | None
    members: list[LinkMember] = field(default_factory=list)
    # Why the group can't be linked as it stands; empty when it can.
    problems: list[str] = field(default_factory=list)

    @property
    def needs_confirmation(self) -> bool:
        """True when linking would change more than a quota somewhere."""
        return any(member.differences for member in self.members)


def plan_links(
    types: Iterable[LeaveType],
    policies: dict[uuid.UUID, LeavePolicy],
    templates: Iterable[LeaveTypeTemplate],
) -> list[LinkGroup]:
    """The groups to link, by name; types already in the library are left alone."""
    entries = {name_key(t.name): t for t in templates}
    by_name: dict[str, list[LeaveType]] = {}
    for leave_type in types:
        if leave_type.template_id is None:
            by_name.setdefault(name_key(leave_type.name), []).append(leave_type)
    taken_codes = {t.code for t in entries.values()}
    groups = []
    for key, members in sorted(by_name.items()):
        existing = entries.get(key)
        if existing is None and len(members) < 2:
            continue
        members.sort(key=lambda t: _policy_order(policies[t.policy_id]))
        groups.append(_group(members, policies, existing, taken_codes))
    return groups


def _group(
    members: list[LeaveType],
    policies: dict[uuid.UUID, LeavePolicy],
    existing: LeaveTypeTemplate | None,
    taken_codes: set[str],
) -> LinkGroup:
    source: LeaveType | LeaveTypeTemplate = existing or members[0]
    rules = {name: getattr(source, name) for name in (*RULE_FIELDS, "annual_quota_days")}
    group = LinkGroup(name=source.name, rules=rules, existing=existing)
    if existing is None and source.code in taken_codes:
        group.problems.append(f"The library already uses the code {source.code} for another type.")
    seen: set[uuid.UUID] = set()
    for leave_type in members:
        policy = policies[leave_type.policy_id]
        if leave_type.policy_id in seen:
            group.problems.append(f"{policy.name} has two types called {source.name}.")
        seen.add(leave_type.policy_id)
        group.members.append(_member(leave_type, policy.name, rules))
    return group


def _member(leave_type: LeaveType, policy_name: str, rules: dict[str, Any]) -> LinkMember:
    shared = {name: rules[name] for name in RULE_FIELDS}
    differences = config_audit.diff(config_audit.snapshot(leave_type, shared), shared)
    # Decimals compare by value (5 == 5.0); None only equals None.
    own_quota = leave_type.annual_quota_days != rules["annual_quota_days"]
    return LinkMember(
        leave_type=leave_type,
        policy_name=policy_name,
        type_name=leave_type.name,
        quota=leave_type.annual_quota_days,
        own_quota=own_quota,
        differences=differences,
    )


def _policy_order(policy: LeavePolicy) -> tuple[Any, str]:
    return (policy.created_at, policy.name)
