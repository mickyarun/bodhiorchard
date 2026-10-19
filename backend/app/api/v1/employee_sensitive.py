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

"""Sensitive details (addresses, IDs, bank) and the access log.

For HR (employees:manage), the owner and the employee themself. Reads are
masked; a value is only shown through reveal, which is logged.
"""

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._employee_helpers import forbid, load_record
from app.core.deps import PermissionSet, get_current_user, get_db, get_permission_set
from app.models.user import User
from app.repositories.employee_sensitive import (
    EmployeeAuditRepository,
    EmployeeSensitiveRepository,
)
from app.repositories.user import UserRepository
from app.schemas.employee_sensitive import (
    AccessLogEntry,
    RevealRequest,
    RevealResponse,
    SensitiveRead,
    SensitiveWrite,
)
from app.schemas.leave import PersonRef
from app.services.employees.record_alerts import alert_text, stage_record_alert
from app.services.employees.sensitive_access import sensitive_access
from app.services.employees.sensitive_details import (
    ALERT_ON,
    Subject,
    masked,
    reveal,
    update_details,
)

router = APIRouter(tags=["employees"])
NO_ACCESS = "Only HR and the employee can see these details."


async def _subject(
    db: AsyncSession, current_user: User, perms: PermissionSet, user_id: uuid.UUID
) -> Subject:
    if not sensitive_access(perms, current_user.id, user_id).details:
        raise forbid(NO_ACCESS)
    profile, _user = await load_record(db, current_user.org_id, user_id)
    return Subject(org_id=current_user.org_id, user_id=user_id, profile=profile)


async def _masked(db: AsyncSession, subject: Subject) -> SensitiveRead:
    row = await EmployeeSensitiveRepository(db, org_id=subject.org_id).for_profile(
        subject.profile.id
    )
    return masked(row, can_edit=True, can_reveal=True)


@router.get("/{user_id}/sensitive", response_model=SensitiveRead)
async def get_sensitive(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> SensitiveRead:
    """Masked addresses, IDs and bank details."""
    return await _masked(db, await _subject(db, current_user, perms, user_id))


@router.put("/{user_id}/sensitive", response_model=SensitiveRead)
async def put_sensitive(
    user_id: uuid.UUID,
    body: SensitiveWrite,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> SensitiveRead:
    """Change some details; the employee is alerted when bank or ID details change."""
    subject = await _subject(db, current_user, perms, user_id)
    changed = await update_details(db, subject, current_user.id, body)
    send = None
    if changed & ALERT_ON:
        text = alert_text(changed & ALERT_ON, current_user.name)
        send = stage_record_alert(db, subject.org_id, user_id, text)
    await db.commit()
    if send:
        send()
    return await _masked(db, subject)


@router.post("/{user_id}/sensitive/reveal", response_model=RevealResponse)
async def reveal_field(
    user_id: uuid.UUID,
    body: RevealRequest,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> RevealResponse:
    """One value in full; the reveal is logged."""
    subject = await _subject(db, current_user, perms, user_id)
    value = await reveal(db, subject, current_user.id, body.field)
    # The reveal must be on record before the value leaves the server.
    await db.commit()
    return RevealResponse(field=body.field, value=value)


@router.get("/{user_id}/access-log", response_model=list[AccessLogEntry])
async def access_log(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> list[AccessLogEntry]:
    """Who looked at or changed this person's sensitive details and documents."""
    access = sensitive_access(perms, current_user.id, user_id)
    if not (access.details or access.documents):
        raise forbid(NO_ACCESS)
    profile, _user = await load_record(db, current_user.org_id, user_id)
    events = await EmployeeAuditRepository(db, org_id=current_user.org_id).for_profile(profile.id)
    names = await UserRepository(db).get_names_by_ids({e.actor_id for e in events})
    return [
        AccessLogEntry(
            action=e.action,
            actor=PersonRef(user_id=e.actor_id, name=names.get(e.actor_id, "Someone")),
            target=e.target,
            at=e.created_at,
        )
        for e in events
    ]
