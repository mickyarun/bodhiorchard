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

"""A policy's side of the library: add a library type, set its quota, let go.

A linked type's rules are the library's; on the policy HR only chooses its
own yearly quota (or the library default) and whether it's switched on.
Letting go keeps the type, its requests and balances, as the policy's own.
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_policy import LeavePolicy
from app.models.leave_type import LeaveType
from app.models.leave_type_template import LeaveTypeTemplate
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_type_template import LeaveTypeTemplateRepository
from app.schemas.leave_library import LinkedTypeWrite
from app.schemas.leave_type import LeaveTypeWrite
from app.services.leave import type_admin
from app.services.leave.errors import LeaveConflictError, LeaveNotFoundError
from app.services.leave.type_admin import TypeLink
from app.services.leave.type_library import linked_body


async def load_entry(
    db: AsyncSession, org_id: uuid.UUID, template_id: uuid.UUID
) -> LeaveTypeTemplate:
    """A library entry in this org, locked for the rest of the transaction, or not found.

    Every write that copies an entry's rules onto a policy type holds this
    lock, as a library edit does, so the copy can't be made from rules an
    edit is replacing (it would miss that edit's update of linked types).
    """
    template = await LeaveTypeTemplateRepository(db, org_id=org_id).get_for_update(template_id)
    if template is None:
        raise LeaveNotFoundError("That library type doesn't exist.")
    return template


async def add_to_policy(
    db: AsyncSession,
    policy: LeavePolicy,
    actor_id: uuid.UUID,
    template: LeaveTypeTemplate,
    body: LinkedTypeWrite,
    *,
    may_approve: bool,
) -> LeaveType:
    """Give the policy a new type that follows ``template``."""
    await _refuse_second_copy(db, policy.id, template)
    return await type_admin.create_type(
        db, policy, actor_id, _body(template, body),
        may_approve=may_approve,
        link=TypeLink(template.id, body.own_quota),
        context={"library": [None, template.name]},
    )  # fmt: skip


async def link_existing(
    db: AsyncSession,
    leave_type: LeaveType,
    actor_id: uuid.UUID,
    template: LeaveTypeTemplate,
    body: LinkedTypeWrite,
    *,
    may_approve: bool,
) -> None:
    """Make a policy's own type follow ``template``; its history stays with it.

    It takes the library's rules (name included); its quota is the
    library's unless ``body`` keeps one of its own. Linking doesn't switch
    it on or off: a retired type stays retired.
    """
    if leave_type.template_id is not None:
        raise LeaveConflictError("This type already follows the library.")
    await _refuse_second_copy(db, leave_type.policy_id, template)
    keep_switch = body.model_copy(update={"is_active": leave_type.is_active})
    await type_admin.update_type(
        db, leave_type, actor_id, _body(template, keep_switch),
        may_approve=may_approve,
        link=TypeLink(template.id, body.own_quota),
        context={"library": [None, template.name]},
    )  # fmt: skip


async def update_linked(
    db: AsyncSession,
    leave_type: LeaveType,
    actor_id: uuid.UUID,
    body: LinkedTypeWrite,
    *,
    may_approve: bool,
) -> None:
    """Set a linked type's own quota (or go back to the default) and on/off."""
    template = await _template_of(db, leave_type)
    await type_admin.update_type(
        db, leave_type, actor_id, _body(template, body),
        may_approve=may_approve, link=TypeLink(template.id, body.own_quota),
    )  # fmt: skip


async def unlink(
    db: AsyncSession, leave_type: LeaveType, actor_id: uuid.UUID, *, may_approve: bool
) -> None:
    """Stop following the library; the type keeps its current rules as its own."""
    template = await _template_of(db, leave_type)
    current = {field: getattr(leave_type, field) for field in LeaveTypeWrite.model_fields}
    await type_admin.update_type(
        db, leave_type, actor_id, LeaveTypeWrite.model_validate(current),
        may_approve=may_approve,
        link=TypeLink(None),
        context={"library": [template.name, None]},
    )  # fmt: skip


async def update_own_type(
    db: AsyncSession,
    leave_type: LeaveType,
    actor_id: uuid.UUID,
    body: LeaveTypeWrite,
    *,
    may_approve: bool,
) -> None:
    """Edit a policy's own type; a linked one is changed in the library."""
    if leave_type.template_id is not None:
        template = await _template_of(db, leave_type)
        raise LeaveConflictError(
            f"This type follows {template.name} in the leave type library. Change its rules "
            "there; on the policy you can set its own quota or switch it off."
        )
    await type_admin.update_type(db, leave_type, actor_id, body, may_approve=may_approve)


def _body(template: LeaveTypeTemplate, body: LinkedTypeWrite) -> LeaveTypeWrite:
    return linked_body(
        template, own_quota=body.own_quota, quota=body.annual_quota_days, is_active=body.is_active
    )


async def _template_of(db: AsyncSession, leave_type: LeaveType) -> LeaveTypeTemplate:
    if leave_type.template_id is None:
        raise LeaveConflictError("This type doesn't follow the library.")
    return await load_entry(db, leave_type.org_id, leave_type.template_id)


async def _refuse_second_copy(
    db: AsyncSession, policy_id: uuid.UUID, template: LeaveTypeTemplate
) -> None:
    repo = LeaveTypeRepository(db, org_id=template.org_id)
    if await repo.linked_on_policy(policy_id, template.id) is not None:
        raise LeaveConflictError(f"{template.name} is already on this policy.")
