"""Pydantic schemas for skill scanning, knowledge search, and profiles."""

import uuid

from pydantic import BaseModel, Field


class ScanRequest(BaseModel):
    """Request to trigger a repository scan."""

    full_rescan: bool = Field(default=False, alias="fullRescan")

    model_config = {"populate_by_name": True}


class ScanResponse(BaseModel):
    """Response after triggering a scan."""

    scan_id: str = Field(alias="scanId")
    status: str = "started"

    model_config = {"populate_by_name": True}


class ScanStatus(BaseModel):
    """Status of a running or completed scan."""

    scan_id: str = Field(alias="scanId")
    status: str
    scan_mode: str = Field(default="full", alias="scanMode")
    progress_pct: int = Field(default=0, alias="progressPct")
    features_indexed: int = Field(default=0, alias="featuresIndexed")
    features_skipped: int = Field(default=0, alias="featuresSkipped")
    profiles_found: int = Field(default=0, alias="profilesFound")
    stale_cleaned: int = Field(default=0, alias="staleCleaned")
    unmatched_authors: list[str] = Field(default_factory=list, alias="unmatchedAuthors")
    synthesis_warning: str | None = Field(default=None, alias="synthesisWarning")
    error: str | None = None

    model_config = {"populate_by_name": True}


class ModuleSkill(BaseModel):
    """A single module skill entry within a profile."""

    name: str
    score: float
    languages: list[str] = []
    touch_count: int = Field(alias="touchCount")

    model_config = {"populate_by_name": True}


class SkillProfileRead(BaseModel):
    """Developer skill profile for API response."""

    user_id: uuid.UUID | None = Field(None, alias="userId")
    user_name: str = Field(alias="userName")
    email: str
    modules: list[ModuleSkill] = []

    model_config = {"populate_by_name": True}


class KnowledgeSearchRequest(BaseModel):
    """Request body for semantic knowledge search."""

    query: str
    limit: int = 10
    category: str | None = None


class KnowledgeSearchResult(BaseModel):
    """A single result from knowledge search."""

    title: str
    content: str
    category: str
    score: float
    source_ref: str | None = Field(None, alias="sourceRef")
    feature_status: str | None = Field(None, alias="featureStatus")

    model_config = {"populate_by_name": True}


class KnowledgeItemRead(BaseModel):
    """Knowledge item for API response."""

    id: uuid.UUID
    title: str
    content: str | None
    category: str
    tags: list[str] | None = None
    source: str | None = None
    source_ref: str | None = Field(None, alias="sourceRef")
    feature_status: str | None = Field(None, alias="featureStatus")
    repo_ids: list[uuid.UUID] = Field(default_factory=list, alias="repoIds")

    model_config = {"populate_by_name": True, "from_attributes": True}
