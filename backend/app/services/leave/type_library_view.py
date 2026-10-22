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

"""Reading the leave type library: entries with the policies that use them."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.leave_type import LeaveType
from app.models.leave_type_template import LeaveTypeTemplate
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.leave_type import LeaveTypeRepository
from app.repositories.leave_type_template import LeaveTypeTemplateRepository
from app.schemas.leave_library import LibraryTypeRead, LibraryTypeUse
from app.schemas.leave_type import LeaveTypeRules


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
