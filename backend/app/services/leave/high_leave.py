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


"""How much leave someone has taken this year, against the policy's lines.

Unlimited leave has no balance to say "that's a lot", so a policy can set a
heads-up line and a warning line (e.g. 15 and 18 days). Leave types count
toward them unless switched off (sick leave usually is). Approved and pending
days count, by the leave year their request starts in. Batched: one query
per policy for any number of people.
"""

import uuid
from collections import defaultdict
from collections.abc import Collection, Sequence
from datetime import date
from decimal import Decimal

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_request import LeaveKind, LeaveRequest
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_usage import LeaveUsageRepository
from app.schemas.leave import HighLeave
from app.services.leave.calendar_math import leave_year_bounds

ZERO = Decimal("0")


def has_lines(policy: LeavePolicy) -> bool:
    """Whether the policy sets a heads-up or warning line at all."""
    return policy.leave_notice_days is not None or policy.leave_warning_days is not None


def assess(policy: LeavePolicy, taken: Decimal) -> HighLeave | None:
    """The level ``taken`` days reach on ``policy``, or None below both lines."""
    notice, warning = policy.leave_notice_days, policy.leave_warning_days
    if warning is not None and taken >= warning:
        level = "warning"
    elif notice is not None and taken >= notice:
        level = "notice"
    else:
        return None
    return HighLeave(level=level, taken=taken, notice_days=notice, warning_days=warning)


async def counted_type_ids(
    db: AsyncSession, policies: Collection[LeavePolicy]
) -> dict[uuid.UUID, set[uuid.UUID]]:
    """Per policy with lines, the ids of its types that count toward them."""
    with_lines = [p for p in policies if has_lines(p)]
    if not with_lines:
        return {}
    org_id = with_lines[0].org_id
    per_policy = await LeaveTypeRepository(db, org_id=org_id).list_for_policies(
        {p.id for p in with_lines}
    )
    return {
        pid: {t.id for t in types if t.counts_toward_warning} for pid, types in per_policy.items()
    }


async def taken_this_year(
    db: AsyncSession, members: Sequence[tuple[uuid.UUID, LeavePolicy]], on: date
) -> dict[uuid.UUID, Decimal]:
    """Counted days per member in the leave year containing ``on``.

    Only members whose policy sets a line are in the result.
    """
    policies = {policy.id: policy for _user, policy in members}
    counted = await counted_type_ids(db, policies.values())
    by_policy: dict[uuid.UUID, list[uuid.UUID]] = defaultdict(list)
    for user_id, policy in members:
        if policy.id in counted:
            by_policy[policy.id].append(user_id)
    out: dict[uuid.UUID, Decimal] = {}
    for policy_id, user_ids in by_policy.items():
        policy, type_ids = policies[policy_id], counted[policy_id]
        year = leave_year_bounds(on, policy.year_start_month)
        totals = dict.fromkeys(user_ids, ZERO)
        if type_ids:
            rows = await LeaveUsageRepository(db, org_id=policy.org_id).leave_days_by_start(
                user_ids, type_ids, year.start, year.end
            )
            for user_id, _type_id, _status, _start, days in rows:
                totals[user_id] += days
        out.update(totals)
    return out


async def with_request(
    db: AsyncSession,
    policy: LeavePolicy,
    user_id: uuid.UUID,
    leave_type_id: uuid.UUID,
    start: date,
    days: Decimal,
) -> HighLeave | None:
    """The level a new request would take someone to, if its type counts."""
    counted = (await counted_type_ids(db, [policy])).get(policy.id, set())
    if leave_type_id not in counted:
        return None
    taken = (await taken_this_year(db, [(user_id, policy)], start)).get(user_id, ZERO)
    return assess(policy, taken + days)


async def for_requests(
    db: AsyncSession, org_id: uuid.UUID, requests: Sequence[LeaveRequest]
) -> dict[uuid.UUID, HighLeave]:
    """For pending leave on counted types: the level the requester is at.

    A pending request already counts as taken, so this is what the approver
    would be agreeing to. One count per (policy, leave year) in the page.
    """
    leave = [r for r in requests if r.kind == LeaveKind.LEAVE and r.leave_type_id is not None]
    policies = await LeavePolicyRepository(db, org_id=org_id).by_ids({r.policy_id for r in leave})
    counted = await counted_type_ids(db, policies.values())
    groups: dict[tuple[uuid.UUID, int], list[LeaveRequest]] = defaultdict(list)
    for r in leave:
        policy = policies.get(r.policy_id)
        if policy is not None and r.leave_type_id in counted.get(policy.id, set()):
            label = leave_year_bounds(r.start_date, policy.year_start_month).label
            groups[(policy.id, label)].append(r)
    out: dict[uuid.UUID, HighLeave] = {}
    for (policy_id, _label), group in groups.items():
        policy = policies[policy_id]
        members = [(r.user_id, policy) for r in group]
        taken = await taken_this_year(db, members, group[0].start_date)
        for r in group:
            level = assess(policy, taken.get(r.user_id, ZERO))
            if level is not None:
                out[r.id] = level
    return out
