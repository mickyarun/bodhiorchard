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

"""Status transitions on an employee record.

Marking someone **exited** also deactivates their account — but only when
the caller is allowed to manage that member (the grant ceiling in
:mod:`app.services.role_grants`). HR can't revoke an engineer's access,
for example, because HR doesn't hold engineering access itself; then the
record is still marked exited and the caller is told an admin has to
deactivate the account.
"""

import uuid
from datetime import date

import structlog
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permission_deps import PermissionSet
from app.models.employee_profile import EmployeeProfile, EmployeeStatus
from app.repositories.user import UserRepository
from app.repositories.user_mcp_token import UserMCPTokenRepository
from app.services.role_grants import assert_can_manage_member

logger = structlog.get_logger(__name__)


async def apply_exit(
    db: AsyncSession,
    *,
    org_id: uuid.UUID,
    actor: PermissionSet,
    actor_id: uuid.UUID,
    profile: EmployeeProfile,
    previous_status: EmployeeStatus,
) -> bool | None:
    """Finish a move to EXITED; returns whether the account was deactivated.

    Returns ``None`` when the status didn't newly become EXITED.
    """
    if profile.status != EmployeeStatus.EXITED or previous_status == EmployeeStatus.EXITED:
        return None
    if profile.date_of_exit is None:
        profile.date_of_exit = date.today()
    if profile.user_id == actor_id:
        # Same rule as Members: you can't deactivate yourself. Without this
        # the owner could lock themselves (possibly the only owner) out.
        logger.info("employee_self_exit_access_left_active", profile_id=str(profile.id))
        return False
    user = await UserRepository(db, org_id=org_id).get_by_id_with_membership(
        profile.user_id, org_id
    )
    if user is None or not user.is_active:
        # Nothing to revoke: the account was already gone or inactive.
        return None
    try:
        await assert_can_manage_member(db, actor=actor, target=user)
    except HTTPException:
        logger.info(
            "employee_exited_access_left_active",
            profile_id=str(profile.id),
            actor_id=str(actor_id),
        )
        return False
    user.is_active = False
    await UserMCPTokenRepository(db).delete_all_for_user(user.id)
    logger.info("employee_exited_access_revoked", profile_id=str(profile.id))
    return True
