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

"""Guard for actions that let the actor sign in as someone else.

Resetting a password (the temporary one goes to the actor) or merging an
account into another both end with the actor holding that person's
identity. Anyone with an employee record can read their own bank
details, IDs and documents, so taking over their identity reveals HR
data: only HR (or the owner) may do these for people with a record,
however the roles otherwise compare.
"""

import uuid

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.user import User
from app.repositories.employee_profile import EmployeeProfileRepository
from app.services.role_grants import assert_can_manage_member

HR_RECORD_ACCESS = ("employees:manage", "employees:documents")


async def assert_can_act_as(
    db: AsyncSession, *, actor: PermissionSet, target: User, org_id: uuid.UUID
) -> None:
    """Raise 403 unless ``actor`` may take over ``target``'s identity.

    ``target`` must carry the transient role attributes from
    ``UserRepository.get_by_id_with_membership``.
    """
    await assert_can_manage_member(db, actor=actor, target=target)
    if actor.has_all(HR_RECORD_ACCESS):  # true for the owner too
        return
    if await EmployeeProfileRepository(db, org_id=org_id).get_by_user(target.id) is not None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"{target.name} has an employee record, so only HR or the org owner "
            "can do this.",
        )
