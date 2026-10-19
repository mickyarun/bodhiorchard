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

"""Shared lookups for the employee routes."""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee_profile import EmployeeProfile
from app.models.user import User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.repositories.user import UserRepository

NO_RECORD = "No employee record for this member yet."


async def load_record(
    db: AsyncSession, org_id: uuid.UUID, user_id: uuid.UUID, *, missing: str = NO_RECORD
) -> tuple[EmployeeProfile, User]:
    """The profile and member for ``user_id`` in this org, or 404."""
    profile = await EmployeeProfileRepository(db, org_id=org_id).get_by_user(user_id)
    user = await UserRepository(db, org_id=org_id).get_by_id_with_membership(user_id, org_id)
    if profile is None or user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=missing)
    return profile, user


def forbid(detail: str) -> HTTPException:
    """A 403 with a user-facing reason."""
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
