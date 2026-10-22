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

"""The org's leave type library: define a type once, reuse it on any policy.

A library entry holds a type's rules and a default yearly quota. Each policy
that uses it has its own ``leave_types`` row (requests and balances point
there), copying every rule from the entry; only the quota may be the
policy's own. Editing an entry rewrites every linked row through
:mod:`type_admin`, so each policy's history records it and the usual rules
hold: only approvers set up self-approval, and how a type is given can't
change once a policy's current year is allocated. One policy refusing
refuses the whole edit, naming that policy.
"""

import uuid
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_type import LeaveType
from app.models.leave_type_template import LeaveTypeTemplate
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_type_template import LeaveTypeTemplateRepository
from app.schemas.leave_library import LibraryTypeRead, LibraryTypeUse, LibraryTypeWrite
from app.schemas.leave_type import LeaveTypeRules, LeaveTypeWrite
from app.services.leave import config_audit, type_admin
from app.services.leave.errors import LeaveConflictError, LeaveError, LeaveInvalidError

# Everything a linked type takes from its library entry; the quota is only a default.
RULE_FIELDS = tuple(field for field in LeaveTypeRules.model_fields if field != "annual_quota_days")


def linked_body(
    template: LeaveTypeTemplate, *, own_quota: bool, quota: Decimal | None, is_active: bool
) -> LeaveTypeWrite:
    """What a policy's type following ``template`` should hold.

    ``quota`` is the policy's own (None = no limit) and only counts when
    ``own_quota`` is set. Refused when the mix breaks a type rule, e.g. a
    self-approving entry with a policy quota of "no limit".
    """
    values: dict[str, object] = {field: getattr(template, field) for field in RULE_FIELDS}
    values["annual_quota_days"] = quota if own_quota else template.annual_quota_days
    try:
        return LeaveTypeWrite.model_validate({**values, "is_active": is_active})
    except ValidationError as exc:
        message = str(exc.errors()[0]["msg"]).removeprefix("Value error, ")
        raise LeaveInvalidError(message) from exc


async def list_library(db: AsyncSession, org_id: uuid.UUID) -> list[LibraryTypeRead]:
    """Every library entry, with the policies that use it."""
    templates = await LeaveTypeTemplateRepository(db, org_id=org_id).list_by_name()
    linked = await LeaveTypeRepository(db, org_id=org_id).linked_to([t.id for t in templates])
    uses = await _uses(db, org_id, linked)
    return [library_read(t, uses.get(t.id, [])) for t in templates]


async def uses_of(db: AsyncSession, template: LeaveTypeTemplate) -> list[LibraryTypeUse]:
    """The policies using one entry."""
    linked = await LeaveTypeRepository(db, org_id=template.org_id).linked_to([template.id])
    return (await _uses(db, template.org_id, linked)).get(template.id, [])


async def create_entry(
    db: AsyncSession, org_id: uuid.UUID, body: LibraryTypeWrite, *, may_approve: bool
) -> LeaveTypeTemplate:
    """Add a type to the library; policies add it from there."""
    type_admin.check_auto_approve(body, may_approve)
    repo = LeaveTypeTemplateRepository(db, org_id=org_id)
    entry = LeaveTypeTemplate(org_id=org_id, **body.model_dump())
    # Checked first for the usual case; the insert catches two adds at once.
    if await repo.code_taken(body.code, exclude=None) or not await repo.create_unique(entry):
        raise LeaveConflictError(f"The code {body.code} is already used in the library.")
    return entry


async def update_entry(
    db: AsyncSession,
    template: LeaveTypeTemplate,
    actor_id: uuid.UUID,
    body: LibraryTypeWrite,
    *,
    may_approve: bool,
) -> None:
    """Edit an entry and every policy type that follows it, all or nothing."""
    type_admin.check_auto_approve(body, may_approve)
    repo = LeaveTypeTemplateRepository(db, org_id=template.org_id)
    if await repo.code_taken(body.code, exclude=template.id):
        raise LeaveConflictError(f"The code {body.code} is already used in the library.")
    after = body.model_dump()
    if not config_audit.diff(config_audit.snapshot(template, after), after):
        return
    for field, value in after.items():
        setattr(template, field, value)
    await db.flush()
    await sync_linked(db, template, actor_id, may_approve=may_approve)


async def sync_linked(
    db: AsyncSession, template: LeaveTypeTemplate, actor_id: uuid.UUID, *, may_approve: bool
) -> None:
    """Bring every type following ``template`` in line with it.

    A refusal on any policy is raised again with that policy's name, so HR
    knows which one blocks the change; the caller's transaction rolls back.
    """
    types = await LeaveTypeRepository(db, org_id=template.org_id).linked_to([template.id])
    policies = await LeavePolicyRepository(db, org_id=template.org_id).by_ids(
        {t.policy_id for t in types}
    )
    for leave_type in types:
        try:
            body = linked_body(
                template,
                own_quota=leave_type.own_quota,
                quota=leave_type.annual_quota_days,
                is_active=leave_type.is_active,
            )
            await type_admin.update_type(
                db, leave_type, actor_id, body,
                may_approve=may_approve, context={"library": template.name},
            )  # fmt: skip
        except LeaveError as exc:
            policy = policies.get(leave_type.policy_id)
            raise type(exc)(f"On {policy.name if policy else 'a policy'}: {exc}") from exc


def library_read(template: LeaveTypeTemplate, uses: list[LibraryTypeUse]) -> LibraryTypeRead:
    """Wire shape of an entry with its uses."""
    rules = {field: getattr(template, field) for field in LeaveTypeRules.model_fields}
    return LibraryTypeRead.model_validate({**rules, "id": template.id, "uses": uses})


async def _uses(
    db: AsyncSession, org_id: uuid.UUID, linked: list[LeaveType]
) -> dict[uuid.UUID, list[LibraryTypeUse]]:
    policies = await LeavePolicyRepository(db, org_id=org_id).by_ids({t.policy_id for t in linked})
    out: dict[uuid.UUID, list[LibraryTypeUse]] = {}
    for t in linked:
        if t.template_id is None:
            continue
        out.setdefault(t.template_id, []).append(
            LibraryTypeUse(
                policy_id=t.policy_id,
                policy_name=policies[t.policy_id].name,
                type_id=t.id,
                own_quota=t.own_quota,
                annual_quota_days=t.annual_quota_days,
                is_active=t.is_active,
            )
        )
    for uses in out.values():
        uses.sort(key=lambda use: use.policy_name.casefold())
    return out
