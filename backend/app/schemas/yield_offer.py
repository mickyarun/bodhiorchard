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

"""Pydantic DTOs for the yield-offer endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, model_validator

from app.models.bud import BUDPriority
from app.models.yield_offer import YieldOfferStatus


class YieldOfferRead(BaseModel):
    """Yield offer payload returned to the BUD board notice / inbox tile."""

    id: uuid.UUID
    incoming_bud_id: uuid.UUID
    incoming_bud_number: int | None = None
    incoming_bud_title: str | None = None
    incoming_bud_priority: BUDPriority | None = None
    yieldable_bud_id: uuid.UUID
    yieldable_bud_number: int | None = None
    yieldable_bud_title: str | None = None
    yieldable_bud_priority: BUDPriority | None = None
    target_user_id: uuid.UUID
    status: YieldOfferStatus
    created_at: datetime

    model_config = {"from_attributes": True}

    @model_validator(mode="before")
    @classmethod
    def _hydrate_bud_fields(cls, data: Any) -> Any:
        """Pull number/title/priority off the joined BUDDocument rows."""
        incoming = getattr(data, "incoming_bud", None)
        if incoming is not None:
            data.incoming_bud_number = incoming.bud_number
            data.incoming_bud_title = incoming.title
            data.incoming_bud_priority = incoming.priority
        yieldable = getattr(data, "yieldable_bud", None)
        if yieldable is not None:
            data.yieldable_bud_number = yieldable.bud_number
            data.yieldable_bud_title = yieldable.title
            data.yieldable_bud_priority = yieldable.priority
        return data
