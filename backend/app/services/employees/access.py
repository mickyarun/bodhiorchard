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

"""Who may see and change which parts of an employee record (pure)."""

import uuid
from dataclasses import dataclass

from app.core.permission_deps import PermissionSet
from app.services.identity_takeover import HR_RECORD_ACCESS

VIEW = "employees:view"
MANAGE = "employees:manage"


@dataclass(frozen=True)
class EmployeeAccess:
    """The caller's rights over one employee record."""

    view: bool
    view_personal: bool
    edit_work: bool
    edit_personal: bool
    edit_managers: bool
    edit_name: bool
    # Generate or reset their sign-in password (never your own: use the
    # normal change-password screen for that).
    reset_password: bool
    # Looser than ``edit_personal`` on purpose: a profile photo is
    # self-expression, not an HR-controlled record like a joining date, so
    # the subject can always change their own.
    edit_avatar: bool


def access_for(perms: PermissionSet, actor_id: uuid.UUID, subject_id: uuid.UUID) -> EmployeeAccess:
    """Resolve the caller's rights over ``subject_id``'s record.

    Work fields and managers are HR's to set, and not on your own record
    (except the owner): otherwise HR could reset their own joining date,
    which drives leave proration, or pick their own approver. Everyone can
    see their own record, including personal fields. A name can be fixed by
    the person themself or by HR (a sign-up handle like "kannan-atoa").
    """
    is_self = actor_id == subject_id
    manage = perms.has(MANAGE)
    edit_own_work = manage and (not is_self or perms.is_owner)
    return EmployeeAccess(
        view=is_self or perms.has(VIEW) or manage,
        view_personal=is_self or manage,
        edit_work=edit_own_work,
        edit_personal=manage,
        edit_managers=edit_own_work,
        edit_name=is_self or manage,
        # The takeover guard's own bar for anyone with a record (HR or owner).
        reset_password=perms.has_all(HR_RECORD_ACCESS) and not is_self,
        edit_avatar=is_self or manage,
    )
