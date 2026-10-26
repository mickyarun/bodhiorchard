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

"""DTOs for the org's leave type library and the policy types linked to it."""

import uuid
from decimal import Decimal

from pydantic import BaseModel, Field

from app.schemas.leave_type import LeaveTypeRules


class LibraryTypeWrite(LeaveTypeRules):
    """Create or edit a library entry; its quota is the default for policies."""


class LibraryTypeUse(BaseModel):
    """One policy that has the library type, with its quota there."""

    policy_id: uuid.UUID
    policy_name: str
    type_id: uuid.UUID
    own_quota: bool
    annual_quota_days: Decimal | None
    is_active: bool


class LibraryTypeRead(LeaveTypeRules):
    """A library entry and the policies that use it."""

    id: uuid.UUID
    uses: list[LibraryTypeUse]


class LinkedTypeWrite(BaseModel):
    """What a policy may set on a library type: its own quota and whether it's on.

    With ``own_quota`` off the library's default applies and
    ``annual_quota_days`` is ignored; on, None means no limit.
    """

    own_quota: bool = False
    annual_quota_days: Decimal | None = Field(None, ge=0, le=365, decimal_places=1)
    is_active: bool = True


class LibraryTypeAdd(LinkedTypeWrite):
    """Add a library type to a policy, or make a policy's own type follow it."""

    template_id: uuid.UUID
