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

"""Employee directory and records: list, create, read, self-service contact.

Open to every member (people workspace): each route checks its own
permission, and a member can always read and update the contact details
of their own record.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
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
from app.models.employee_profile import EmployeeProfile, EmployeeStatus
from app.models.user import User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.user import UserRepository
from app.schemas.employee import (
    DirectoryEntry,
    EmployeeContact,
    EmployeeCreate,
    EmployeeRead,
    MemberCandidate,
)
from app.services.employees.access import MANAGE, VIEW, access_for
from app.services.employees.views import directory_entries, employee_read

router = APIRouter(tags=["employees"])

OWN_RECORD_MISSING = "HR hasn't set up your employee record yet."


@router.get(
    "", response_model=list[DirectoryEntry], dependencies=[Depends(require_permissions(VIEW))]
)
async def list_employees(
    q: str | None = Query(None, max_length=100),
    department: str | None = Query(None, max_length=150),
    employee_status: EmployeeStatus | None = Query(None, alias="status"),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[DirectoryEntry]:
    """The employee directory: members who have a record."""
    rows = await EmployeeProfileRepository(db, org_id=current_user.org_id).list_directory(
        search=q, department=department, status=employee_status
    )
    return await directory_entries(db, org_id=current_user.org_id, rows=rows)


@router.get(
    "/candidates",
    response_model=list[MemberCandidate],
    dependencies=[Depends(require_permissions(MANAGE))],
)
async def list_candidates(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[MemberCandidate]:
    """Active members without a record — the "Add employee" picker."""
    repo = EmployeeProfileRepository(db, org_id=current_user.org_id)
    return [
        MemberCandidate(user_id=m.user_id, name=m.name, email=m.email)
        for m in await repo.list_members_without_profile()
    ]


@router.post("", response_model=EmployeeRead, status_code=status.HTTP_201_CREATED)
async def create_employee(
    body: EmployeeCreate,
    current_user: User = Depends(require_permissions(MANAGE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """Create the employee record for an existing member."""
    org_id = current_user.org_id
    access = access_for(perms, current_user.id, body.user_id)
    if not access.edit_work:
        raise forbid("You can't create your own employee record. Ask another HR member.")
    member = await UserRepository(db, org_id=org_id).get_by_id_with_membership(
        body.user_id, org_id
    )
    if member is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found.")
    repo = EmployeeProfileRepository(db, org_id=org_id)
    if await repo.get_by_user(body.user_id) is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="This member already has a record."
        )
    code = body.work.employee_code
    if code and await repo.code_taken(code, exclude_profile=None):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=f"Employee code {code} is already used."
        )
    try:
        profile = await repo.create(
            EmployeeProfile(org_id=org_id, user_id=body.user_id, **body.work.model_dump())
        )
    except IntegrityError as exc:
        # Lost a race with a concurrent create (same member or same code).
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This member or employee code already has a record.",
        ) from exc
    return await employee_read(db, org_id=org_id, profile=profile, user=member, access=access)


@router.get("/me", response_model=EmployeeRead)
async def read_my_record(
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """The caller's own record."""
    org_id = current_user.org_id
    profile, user = await load_record(db, org_id, current_user.id, missing=OWN_RECORD_MISSING)
    access = access_for(perms, current_user.id, current_user.id)
    return await employee_read(db, org_id=org_id, profile=profile, user=user, access=access)


@router.patch("/me", response_model=EmployeeRead)
async def update_my_contact(
    body: EmployeeContact,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """Update the contact and emergency fields on the caller's own record."""
    org_id = current_user.org_id
    profile, user = await load_record(db, org_id, current_user.id, missing=OWN_RECORD_MISSING)
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(profile, field, value)
    await db.flush()
    access = access_for(perms, current_user.id, current_user.id)
    return await employee_read(db, org_id=org_id, profile=profile, user=user, access=access)


@router.get("/{user_id}", response_model=EmployeeRead)
async def read_employee(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeRead:
    """One record; personal fields only for HR, the owner and the employee."""
    access = access_for(perms, current_user.id, user_id)
    if not access.view:
        raise forbid("You don't have access to employee records.")
    org_id = current_user.org_id
    profile, user = await load_record(db, org_id, user_id)
    return await employee_read(db, org_id=org_id, profile=profile, user=user, access=access)
