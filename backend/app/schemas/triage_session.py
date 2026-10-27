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

"""Pydantic schemas for triage session endpoints."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, computed_field

from app.models.bud import BUDPriority
from app.services.triage_priority import normalize_triage_priority


class TriageSessionRead(BaseModel):
    """Response schema for a triage session."""

    id: uuid.UUID
    org_id: uuid.UUID
    slack_channel: str
    thread_ts: str
    requester_slack_id: str
    requester_name: str | None = None
    requester_display_name: str | None = None
    original_text: str | None = None
    status: str
    priority: str | None = None
    feature_name: str | None = None
    triage_context: dict[str, Any] | None = None
    bud_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

    @computed_field  # type: ignore[prop-decorator]
    @property
    def bud_priority(self) -> BUDPriority:
        """The priority the BUD gets if this request is approved.

        A preview only, so an unknown value isn't logged here; approval logs it.
        """
        return normalize_triage_priority(self.priority, log_unknown=False)


class TriageApprovalRequest(BaseModel):
    """Request schema for approving or rejecting a triage session."""

    notes: str | None = Field(None, max_length=2000)
