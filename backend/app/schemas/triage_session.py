"""Pydantic schemas for triage session endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
    triage_context: dict | None = None
    bud_id: uuid.UUID | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TriageApprovalRequest(BaseModel):
    """Request schema for approving or rejecting a triage session."""

    notes: str | None = Field(None, max_length=2000)
