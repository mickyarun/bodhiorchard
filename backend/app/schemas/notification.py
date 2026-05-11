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

"""Notification request/response schemas."""

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class NotificationRead(BaseModel):
    """Notification response schema with camelCase aliases for frontend."""

    id: uuid.UUID
    user_id: uuid.UUID = Field(alias="userId")
    type: str
    title: str
    message: str | None = None
    deep_link: str | None = Field(None, alias="deepLink")
    job_id: str | None = Field(None, alias="jobId")
    job_type: str | None = Field(None, alias="jobType")
    is_read: bool = Field(alias="isRead")
    is_dismissed: bool = Field(alias="isDismissed")
    created_at: datetime = Field(alias="createdAt")
    # Structured payload — race invites put {hostName, hostUserId, roomId,
    # distanceM} here so the toast / bell dropdown don't have to re-parse
    # the message string.
    meta: dict[str, Any] | None = None

    model_config = {"from_attributes": True, "populate_by_name": True}
