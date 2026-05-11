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

"""Pydantic schemas for the Features API.

Replaces the legacy ``KnowledgeItemRead`` / ``KnowledgeItemPage`` shapes
exposed under ``/v1/skills/knowledge``. Aliased camelCase fields match
the Vue 3 frontend convention; ``populate_by_name=True`` lets internal
Python callers construct via snake_case names.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_BASE_CONFIG = ConfigDict(populate_by_name=True, from_attributes=True)


class PrimaryLinkRead(BaseModel):
    """The single PRIMARY junction row that owns a feature.

    The repo where the feature was synthesised, plus the source-side
    file map captured at synthesis time. Always present for an active
    feature; the API treats its absence as a data-integrity violation
    surfaced by the audit.
    """

    repo_id: uuid.UUID = Field(alias="repoId")
    repo_name: str = Field(alias="repoName")
    code_locations: dict[str, list[str]] | None = Field(default=None, alias="codeLocations")

    model_config = _BASE_CONFIG


class BackendLinkRead(BaseModel):
    """One BACKEND junction row — a backend repo this feature depends on.

    Populated by the per-scan ``backend_link`` stage by matching the
    feature's frontend route calls against backend repos' declared
    routes. The Features-tab inline expand panel renders each link as
    "↳ <repo_name>" plus the matched ``api_paths`` underneath.
    """

    repo_id: uuid.UUID = Field(alias="repoId")
    repo_name: str = Field(alias="repoName")
    api_paths: list[str] = Field(default_factory=list, alias="apiPaths")
    code_locations: dict[str, list[str]] | None = Field(default=None, alias="codeLocations")

    model_config = _BASE_CONFIG


class FeatureRead(BaseModel):
    """One feature for the Features-tab API."""

    id: uuid.UUID
    feature_title: str = Field(alias="featureTitle")
    description: str
    capabilities: dict[str, Any] = Field(default_factory=dict)
    cluster_names: list[str] = Field(default_factory=list, alias="clusterNames")
    tags: list[str] = Field(default_factory=list)
    feature_status: str | None = Field(default=None, alias="featureStatus")
    source: str | None = None
    source_ref: str | None = Field(default=None, alias="sourceRef")
    synthesized_at: datetime = Field(alias="synthesizedAt")
    primary: PrimaryLinkRead
    backend_links: list[BackendLinkRead] = Field(default_factory=list, alias="backendLinks")

    model_config = _BASE_CONFIG


class FeaturePage(BaseModel):
    """Paginated feature list (the original ``/v1/features`` shape)."""

    items: list[FeatureRead]
    total: int

    model_config = _BASE_CONFIG


class FeaturesByRepoRead(BaseModel):
    """One repo's features grouped together for the redesigned tab."""

    repo_id: uuid.UUID = Field(alias="repoId")
    repo_name: str = Field(alias="repoName")
    feature_count: int = Field(alias="featureCount")
    features: list[FeatureRead] = Field(default_factory=list)

    model_config = _BASE_CONFIG


class RepoContributorRead(BaseModel):
    """One row of a repo's top-contributors panel."""

    user_id: uuid.UUID | None = Field(default=None, alias="userId")
    actor_name: str = Field(alias="actorName")
    commit_count: int = Field(alias="commitCount")
    files_changed: int = Field(alias="filesChanged")

    model_config = _BASE_CONFIG


class FeatureMatchLogRead(BaseModel):
    """One reconciler match decision — borderline-tuning surface."""

    id: uuid.UUID
    repo_id: uuid.UUID = Field(alias="repoId")
    head_sha: str = Field(alias="headSha")
    match_via: str = Field(alias="matchVia")
    score: float
    feature_title: str = Field(alias="featureTitle")
    matched_feature_id: uuid.UUID | None = Field(default=None, alias="matchedFeatureId")
    decision: str
    created_at: datetime = Field(alias="createdAt")

    model_config = _BASE_CONFIG
