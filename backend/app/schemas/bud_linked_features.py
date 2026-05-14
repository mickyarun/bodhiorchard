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

"""Pydantic schemas for the BUD↔feature linkage endpoints.

Split out of :mod:`app.schemas.bud` so the linked-feature DTOs live next
to their endpoint (``api/v1/bud_linked_features.py``) rather than in the
core BUD CRUD module. The shape is camelCase via ``model_config`` so the
frontend consumes it without renaming.
"""

import uuid

from pydantic import BaseModel, Field


class LinkedFeatureRead(BaseModel):
    """One feature linked to a BUD, with PRIMARY-repo metadata flattened.

    Shape is camelCase via ``model_config`` aliases so the frontend can
    consume it without renaming. ``code_locations`` is the JSONB blob
    from the PRIMARY :class:`FeatureToRepo` row — null when no PRIMARY
    junction exists (rare; happens for legacy or BUD-authored features).
    """

    id: uuid.UUID
    title: str = Field(..., alias="title")
    link_type: str = Field(..., alias="linkType")
    source: str
    repo_id: uuid.UUID | None = Field(default=None, alias="repoId")
    repo_name: str | None = Field(default=None, alias="repoName")
    code_locations: dict[str, list[str]] | None = Field(default=None, alias="codeLocations")

    model_config = {"populate_by_name": True}


class LinkFeaturesRequest(BaseModel):
    """Body for POST /buds/{bud_id}/linked-features.

    ``feature_ids`` is treated as a set — duplicates are dropped, and
    ids that don't belong to the requesting org or are inactive are
    silently filtered at the repository layer.
    """

    feature_ids: list[uuid.UUID] = Field(..., min_length=1, alias="featureIds")

    model_config = {"populate_by_name": True}


class LinkFeaturesResponse(BaseModel):
    """Response for POST /buds/{bud_id}/linked-features."""

    inserted_count: int = Field(..., alias="insertedCount")
    inserted_feature_ids: list[uuid.UUID] = Field(..., alias="insertedFeatureIds")

    model_config = {"populate_by_name": True}
