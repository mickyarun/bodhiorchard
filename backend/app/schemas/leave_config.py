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

"""DTOs for the leave configuration trail and allocation recalculation."""

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, Field

from app.models.leave_config_event import LeaveConfigAction
from app.schemas.leave import PersonRef
from app.schemas.leave_policy import MemberBalances


class ConfigEventRead(BaseModel):
    """One change to a policy or its leave types."""

    id: uuid.UUID
    action: LeaveConfigAction
    actor: PersonRef
    at: datetime
    # {"field": [old, new]}; type events also carry {"type": "<code>"}.
    changes: dict[str, Any]


class Recalculate(BaseModel):
    """Recalculate one member's frozen allocation for a leave type and year."""

    leave_type_id: uuid.UUID
    leave_year: int | None = Field(None, ge=2000, le=2100)


class RecalculateResult(BaseModel):
    """What the recalculation changed, and the member's balances after it."""

    frozen: Decimal
    recalculated: Decimal
    correction: Decimal
    balances: MemberBalances
