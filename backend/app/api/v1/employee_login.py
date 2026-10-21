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

"""HR generates (never set) or resets (already set) someone's sign-in password.

From their employee record. The new password is temporary: they must
change it when they next sign in. HR shares it by Slack DM, email (their
own mail app, prefilled) or copy; it's never stored in plain text.
"""

import uuid

import structlog
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1._employee_helpers import forbid, load_record
from app.core.deps import PermissionSet, get_current_user, get_db, get_permission_set
from app.models.user import User
from app.repositories.organization import OrganizationRepository
from app.schemas.employee_login import (
    EmployeeLoginRead,
    EmployeePasswordRequest,
    EmployeePasswordResult,
    PasswordAction,
)
from app.services.employees.access import access_for
from app.services.identity_takeover import assert_can_act_as
from app.services.member_credentials import (
    has_own_password,
    login_url,
    send_credentials_slack,
    set_temporary_password,
)

router = APIRouter(tags=["employees"])
logger = structlog.get_logger(__name__)

CANT_RESET = "Only HR can set someone else's password, and not their own."


async def _target(db: AsyncSession, user: User, perms: PermissionSet, user_id: uuid.UUID) -> User:
    """The person, after checking the caller may take over their sign-in."""
    if not access_for(perms, user.id, user_id).reset_password:
        raise forbid(CANT_RESET)
    _profile, target = await load_record(db, user.org_id, user_id)
    await assert_can_act_as(db, actor=perms, target=target, org_id=user.org_id)
    return target


def _action(target: User) -> PasswordAction:
    return "reset" if has_own_password(target) else "generate"


@router.get("/{user_id}/login", response_model=EmployeeLoginRead)
async def get_employee_login(
    user_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeeLoginRead:
    """Whether HR's button generates or resets, and where it can be sent."""
    target = await _target(db, current_user, perms, user_id)
    return EmployeeLoginRead(
        action=_action(target), email=target.email, slack_linked=bool(target.slack_id)
    )


@router.post("/{user_id}/login/password", response_model=EmployeePasswordResult)
async def set_employee_password(
    user_id: uuid.UUID,
    body: EmployeePasswordRequest | None = None,
    current_user: User = Depends(get_current_user),
    perms: PermissionSet = Depends(get_permission_set),
    db: AsyncSession = Depends(get_db),
) -> EmployeePasswordResult:
    """Set a new temporary password and, if asked, DM it on Slack."""
    target = await _target(db, current_user, perms, user_id)
    action = _action(target)
    password = set_temporary_password(target)
    await db.commit()
    logger.info(
        "employee_password_set",
        user_id=str(user_id),
        action=action,
        set_by=str(current_user.id),
    )
    sent, error = None, None
    if body and body.send_via == "slack":
        org = await OrganizationRepository(db).get_for_user(current_user)
        sent, error = await send_credentials_slack(org, target, password)
    return EmployeePasswordResult(
        action=action,
        password=password,
        login_url=login_url(),
        slack_sent=sent,
        slack_error=error,
    )
