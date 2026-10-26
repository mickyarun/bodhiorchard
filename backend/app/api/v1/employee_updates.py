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

"""Edits to employee records: work details, personal details, managers (HR),
and the person's name (HR, or the person themself)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._employee_helpers import forbid, load_record
from app.core.deps import (
    PermissionSet,
    get_current_user,
    get_db,
    get_permission_set,
    require_permissions,
)
from app.models.user import User
from app.repositories.base import violated_constraint
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.employee_reporting_manager import EmployeeReportingManagerRepository
from app.schemas.employee import (
    CelebrationPrefsUpdate,
    EmployeePersonal,
    EmployeeRead,
    EmployeeWork,
    ManagersUpdate,
    NameUpdate,
)
from app.services.employees.access import MANAGE, access_for
from app.services.employees.lifecycle import apply_exit
from app.services.employees.managers import (
    ManagerChoice,
    ManagerValidationError,
    validate_managers,
)
from app.services.employees.offices import check_office, follow_office_policy
from app.services.employees.views import employee_read

CODE_CONSTRAINT = "uq_employee_profiles_org_code"
OFFICE_CONSTRAINT = "fk_employee_profiles_office"

router = APIRouter(tags=["employees"])

OWN_WORK = "You can't change your own work details or managers. Ask another HR member."
# Gender decides who can use some leave types (period leave), so it's guarded
# like work details: nobody sets their own and with it their own entitlement.
OWN_GENDER = (
    "You can't change your own gender here: it decides which leave you get. Ask another HR member."
)


@router.put("/{user_id}/name", response_model=EmployeeRead)
async def update_name(
    user_id: uuid.UUID,
    body: NameUpdate,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """Fix a person's name (theirs, or anyone's for HR). It's the account's
    name, so it changes everywhere they appear."""
    access = access_for(perms, current_user.id, user_id)
    if not access.edit_name:
        raise forbid("Only HR or the person themself can change their name.")
    org_id = current_user.org_id
    profile, user = await load_record(db, org_id, user_id)
    user.name = body.name
    await db.flush()
    return await employee_read(db, org_id=org_id, profile=profile, user=user, access=access)


@router.put("/{user_id}/work", response_model=EmployeeRead)
async def update_work(
    user_id: uuid.UUID,
    body: EmployeeWork,
    current_user: User = Depends(require_permissions(MANAGE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """Replace the work details. Moving to "exited" may deactivate the account."""
    access = access_for(perms, current_user.id, user_id)
    if not access.edit_work:
        raise forbid(OWN_WORK)
    org_id = current_user.org_id
    profile, user = await load_record(db, org_id, user_id)
    code = body.employee_code
    repo = EmployeeProfileRepository(db, org_id=org_id)
    if code and await repo.code_taken(code, exclude_profile=profile.id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Employee code {code} is already used."
        )
    office = await check_office(db, org_id, body.office_id)
    previous_status, previous_office_id = profile.status, profile.office_id
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    revoked = await apply_exit(
        db,
        org_id=org_id,
        actor=perms,
        actor_id=current_user.id,
        profile=profile,
        previous_status=previous_status,
    )
    try:
        await db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) == CODE_CONSTRAINT:  # a concurrent save took the code
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Employee code {code} is already used.",
            ) from exc
        if violated_constraint(exc) == OFFICE_CONSTRAINT:  # deleted meanwhile
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="That office was just deleted. Pick another.",
            ) from exc
        raise
    await follow_office_policy(
        db,
        profile=profile,
        office=office,
        previous_office_id=previous_office_id,
        actor_id=current_user.id,
        perms=perms,
    )
    return await employee_read(
        db, org_id=org_id, profile=profile, user=user, access=access, access_revoked=revoked
    )


@router.put("/{user_id}/personal", response_model=EmployeeRead)
async def update_personal(
    user_id: uuid.UUID,
    body: EmployeePersonal,
    current_user: User = Depends(require_permissions(MANAGE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """Replace the personal details (HR). Not your own gender, unless you're the owner."""
    org_id = current_user.org_id
    profile, user = await load_record(db, org_id, user_id)
    own = user_id == current_user.id and not perms.is_owner
    if own and body.gender != profile.gender:
        raise forbid(OWN_GENDER)
    for field, value in body.model_dump().items():
        setattr(profile, field, value)
    await db.flush()
    access = access_for(perms, current_user.id, user_id)
    return await employee_read(db, org_id=org_id, profile=profile, user=user, access=access)


@router.patch("/{user_id}/celebrations", response_model=EmployeeRead)
async def update_celebration_prefs(
    user_id: uuid.UUID,
    body: CelebrationPrefsUpdate,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """Mute or unmute someone's birthday / work-anniversary announcement.

    The opt-out belongs to the employee: they may switch either one on or
    off. HR may mute on someone's behalf (a request made in person, say) but
    never unmute — only the person can agree to having their date announced
    again. Nobody else may change it.
    """
    access = access_for(perms, current_user.id, user_id)
    changes = body.model_dump(exclude_unset=True, exclude_none=True)
    if not access.is_self:
        if not access.edit_personal:
            raise forbid("Only HR or the person themself can change this.")
        if any(changes.values()):
            raise forbid("Only the person themself can turn an announcement back on.")
    org_id = current_user.org_id
    profile, user = await load_record(db, org_id, user_id)
    for field, value in changes.items():
        setattr(profile, field, value)
    await db.flush()
    return await employee_read(db, org_id=org_id, profile=profile, user=user, access=access)


@router.put("/{user_id}/managers", response_model=EmployeeRead)
async def update_managers(
    user_id: uuid.UUID,
    body: ManagersUpdate,
    current_user: User = Depends(require_permissions(MANAGE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """Replace the reporting managers; any one of them approves leave."""
    access = access_for(perms, current_user.id, user_id)
    if not access.edit_managers:
        raise forbid(OWN_WORK)
    org_id = current_user.org_id
    profile, user = await load_record(db, org_id, user_id)
    links = EmployeeReportingManagerRepository(db, org_id=org_id)
    requested = [ManagerChoice(user_id=m.user_id, is_primary=m.is_primary) for m in body.managers]
    current = (await links.list_for_profiles([profile.id])).get(profile.id, [])
    try:
        pairs = validate_managers(
            user_id,
            requested,
            active_members=await links.active_member_ids([c.user_id for c in requested]),
            edges=await links.reporting_edges(),
            existing={link.user_id for link in current},
        )
    except ManagerValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    await links.replace_for_profile(profile.id, pairs)
    return await employee_read(db, org_id=org_id, profile=profile, user=user, access=access)
