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

"""Link an org's existing same-named leave types into the library.

Run as a dry run first: every group is linked inside the transaction and
then rolled back, so the report shows what applying would do, including a
policy that refuses (e.g. how a type is given can't change once its year is
allocated). Groups whose linking would change more than a quota are only
kept once the owner accepts those differences. Safe to run again:
linked types are left alone and names with an entry link to it.
"""

import uuid
from dataclasses import dataclass
from enum import StrEnum

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_type_template import LeaveTypeTemplate
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_type_template import LeaveTypeTemplateRepository
from app.schemas.leave_library import LibraryTypeWrite, LinkedTypeWrite
from app.services.leave import type_library, type_linking
from app.services.leave.errors import LeaveError
from app.services.leave.type_link_plan import LinkGroup, plan_links


class LinkStatus(StrEnum):
    """What became of one group."""

    LINKED = "linked"
    # Dry run: it would link as listed.
    READY = "ready"
    # Linking would change more than a quota; the owner hasn't accepted it yet.
    NEEDS_CONFIRMATION = "needs confirmation"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class LinkOutcome:
    """One group and what happened to it."""

    group: LinkGroup
    status: LinkStatus
    reason: str = ""


async def link_existing_types(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    *,
    apply: bool,
    accept_differences: bool,
) -> list[LinkOutcome]:
    """Plan, link each group in its own savepoint, then commit or roll back.

    The actor is recorded on every policy's history event and is trusted
    as an approver (the owner runs this), so self-approving types link too.
    """
    types = await LeaveTypeRepository(db, org_id=org_id).list_all()
    policies = {p.id: p for p in await LeavePolicyRepository(db, org_id=org_id).list_all()}
    templates = await LeaveTypeTemplateRepository(db, org_id=org_id).list_by_name()
    outcomes = []
    for group in plan_links(types, policies, templates):
        outcomes.append(await _link(db, org_id, actor_id, group, apply, accept_differences))
    if apply:
        await db.commit()
    else:
        await db.rollback()
    return outcomes


async def _link(
    db: AsyncSession,
    org_id: uuid.UUID,
    actor_id: uuid.UUID,
    group: LinkGroup,
    apply: bool,
    accept_differences: bool,
) -> LinkOutcome:
    """Link one group in a savepoint, kept only when it may be.

    A group needing confirmation is still tried, so a refusal shows up
    before the owner confirms, then undone: the dry run and the apply skip
    the same groups, and a skipped group can't affect the ones after it.
    """
    if group.problems:
        return LinkOutcome(group, LinkStatus.BLOCKED, " ".join(group.problems))
    keep = accept_differences or not group.needs_confirmation
    savepoint = await db.begin_nested()
    try:
        template = group.existing or await _create_entry(db, org_id, group)
        await _link_members(db, actor_id, template, group)
    except (LeaveError, ValidationError) as exc:
        await savepoint.rollback()
        return LinkOutcome(group, LinkStatus.BLOCKED, str(exc))
    if not keep:
        await savepoint.rollback()
        return LinkOutcome(group, LinkStatus.NEEDS_CONFIRMATION)
    await savepoint.commit()
    return LinkOutcome(group, LinkStatus.LINKED if apply else LinkStatus.READY)


async def _create_entry(
    db: AsyncSession, org_id: uuid.UUID, group: LinkGroup
) -> LeaveTypeTemplate:
    body = LibraryTypeWrite.model_validate(group.rules)
    return await type_library.create_entry(db, org_id, body, may_approve=True)


async def _link_members(
    db: AsyncSession, actor_id: uuid.UUID, template: LeaveTypeTemplate, group: LinkGroup
) -> None:
    for member in group.members:
        own = member.leave_type
        body = LinkedTypeWrite(
            own_quota=member.own_quota,
            annual_quota_days=own.annual_quota_days,
            is_active=own.is_active,
        )
        try:
            await type_linking.link_existing(db, own, actor_id, template, body, may_approve=True)
        except LeaveError as exc:
            raise type(exc)(f"On {member.policy_name}: {exc}") from exc
