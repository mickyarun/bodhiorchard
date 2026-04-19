# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Notification request/response schemas."""

import uuid
from datetime import datetime

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

    model_config = {"from_attributes": True, "populate_by_name": True}
