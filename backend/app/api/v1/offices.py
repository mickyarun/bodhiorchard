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

"""Office locations. Anyone can list them; HR (employees:manage) edits them.

An office's leave policy moves the people placed there onto it, so setting
or changing it also needs leave:configure.
"""

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user, get_db, get_permission_set, require_permissions
from app.core.permission_deps import PermissionSet
from app.models.office_location import OfficeLocation
from app.models.user import User
from app.repositories.base import violated_constraint
from app.repositories.leave_policy import LeavePolicyRepository
from app.repositories.office_location import OfficeLocationRepository
from app.schemas.office import OfficeRead, OfficeWrite
from app.services.employees.access import MANAGE
from app.services.leave.permissions import CONFIGURE

router = APIRouter(tags=["employees"])
NAME_CONSTRAINT = "uq_office_locations_org_name"
PLACED_CONSTRAINT = "fk_employee_profiles_office"
PEOPLE_THERE = "People work from this office, including former employees. Move them first."


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


async def _list(db: AsyncSession, org_id: uuid.UUID) -> list[OfficeRead]:
    rows = await OfficeLocationRepository(db, org_id=org_id).list_with_counts()
    policies = await LeavePolicyRepository(db, org_id=org_id).by_ids(
        {o.leave_policy_id for o, _ in rows if o.leave_policy_id}
    )
    return [
        OfficeRead(
            id=office.id,
            name=office.name,
            city=office.city,
            country_code=office.country_code,
            leave_policy_id=office.leave_policy_id,
            leave_policy_name=policies[office.leave_policy_id].name
            if office.leave_policy_id in policies
            else None,
            employee_count=count,
        )
        for office, count in rows
    ]


async def _check(
    db: AsyncSession,
    org_id: uuid.UUID,
    body: OfficeWrite,
    *,
    perms: PermissionSet,
    current: OfficeLocation | None,
) -> None:
    exclude = current.id if current else None
    if await OfficeLocationRepository(db, org_id=org_id).name_taken(body.name, exclude=exclude):
        raise _conflict(f"There's already an office called {body.name}.")
    previous = current.leave_policy_id if current else None
    if body.leave_policy_id != previous and not perms.has(CONFIGURE):
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, detail="Only people who manage leave can set its policy."
        )
    if body.leave_policy_id is not None:
        policy = await LeavePolicyRepository(db, org_id=org_id).get_by_id(body.leave_policy_id)
        if policy is None:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Pick one of your leave policies."
            )


async def _load(db: AsyncSession, org_id: uuid.UUID, office_id: uuid.UUID) -> OfficeLocation:
    office = await OfficeLocationRepository(db, org_id=org_id).get_by_id(office_id)
    if office is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Office not found.")
    return office


@router.get("", response_model=list[OfficeRead])
async def list_offices(
    current_user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)
) -> list[OfficeRead]:
    """Every office, by name."""
    return await _list(db, current_user.org_id)


@router.post("", response_model=list[OfficeRead], status_code=status.HTTP_201_CREATED)
async def create_office(
    body: OfficeWrite,
    current_user: User = Depends(require_permissions(MANAGE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> list[OfficeRead]:
    """Add an office; returns the updated list."""
    await _check(db, current_user.org_id, body, perms=perms, current=None)
    try:
        await OfficeLocationRepository(db, org_id=current_user.org_id).create(
            OfficeLocation(org_id=current_user.org_id, **body.model_dump())
        )
    except IntegrityError as exc:
        if violated_constraint(exc) != NAME_CONSTRAINT:
            raise
        # A same-named office saved at the same moment.
        raise _conflict(f"There's already an office called {body.name}.") from exc
    return await _list(db, current_user.org_id)


@router.put("/{office_id}", response_model=list[OfficeRead])
async def update_office(
    office_id: uuid.UUID,
    body: OfficeWrite,
    current_user: User = Depends(require_permissions(MANAGE)),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> list[OfficeRead]:
    """Change an office. A new leave policy applies to people placed there from now on."""
    office = await _load(db, current_user.org_id, office_id)
    await _check(db, current_user.org_id, body, perms=perms, current=office)
    for field, value in body.model_dump().items():
        setattr(office, field, value)
    try:
        await db.flush()
    except IntegrityError as exc:
        if violated_constraint(exc) != NAME_CONSTRAINT:
            raise
        raise _conflict(f"There's already an office called {body.name}.") from exc
    return await _list(db, current_user.org_id)


@router.delete("/{office_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_office(
    office_id: uuid.UUID,
    current_user: User = Depends(require_permissions(MANAGE)),
    db: AsyncSession = Depends(get_db),
) -> None:
    """Delete an office nobody works from."""
    repo = OfficeLocationRepository(db, org_id=current_user.org_id)
    office = await _load(db, current_user.org_id, office_id)
    if await repo.has_people(office.id):
        raise _conflict(PEOPLE_THERE)
    try:
        await repo.delete(office)
    except IntegrityError as exc:
        if violated_constraint(exc) != PLACED_CONSTRAINT:
            raise
        raise _conflict(PEOPLE_THERE) from exc  # someone was placed here meanwhile
