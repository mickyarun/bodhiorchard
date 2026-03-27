"""Pydantic schemas for QA test case management and evidence."""

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class ManualTestResultUpdate(BaseModel):
    """Request body for updating a manual test case result."""

    test_case_id: str = Field(..., max_length=20, examples=["MTC-001"])
    result: Literal["pass", "fail", "blocked", "skipped"]
    notes: str | None = Field(None, max_length=2000)


class TestEvidenceRead(BaseModel):
    """Response schema for a single evidence file."""

    id: uuid.UUID
    test_case_id: str
    filename: str
    mime_type: str
    uploaded_by: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}


class QATestCasesResponse(BaseModel):
    """Response schema for all QA test cases on a BUD."""

    automation_test_cases: list[dict[str, Any]] = []
    manual_test_cases: list[dict[str, Any]] = []
    execution_plan_md: str = ""
    evidence: list[TestEvidenceRead] = []


class QASummaryResponse(BaseModel):
    """Summary counts for QA test case progress."""

    total_automation: int = 0
    total_manual: int = 0
    manual_pass: int = 0
    manual_fail: int = 0
    manual_blocked: int = 0
    manual_skipped: int = 0
    manual_pending: int = 0
    evidence_count: int = 0
