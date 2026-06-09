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

"""Pydantic schemas for the Teams REST surface."""

import uuid

from pydantic import BaseModel, ConfigDict, Field

from app.models.team import TeamStatus


class TeamMemberRead(BaseModel):
    """Joined view of a team membership row + the user it points at."""

    model_config = ConfigDict(from_attributes=True)

    user_id: uuid.UUID
    name: str
    email: str
    role: str  # canonical UserRole value (e.g. "developer", "pm")
    role_name: str | None = None  # raw role row name (custom roles)
    avatar_url: str | None = None
    is_active: bool


class TeamRepoRead(BaseModel):
    """Joined view of a team-repo mapping row + the tracked repo."""

    model_config = ConfigDict(from_attributes=True)

    repo_id: uuid.UUID
    name: str
    path: str
    github_full_name: str | None = None


class TeamRead(BaseModel):
    """Full team representation with joined members + repos.

    Member and repo lists are returned in stable name order so a
    re-render after a no-op PATCH doesn't reshuffle the UI.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: str | None = None
    status: TeamStatus
    members: list[TeamMemberRead] = Field(default_factory=list)
    repos: list[TeamRepoRead] = Field(default_factory=list)


class TeamSummary(BaseModel):
    """Minimal team representation for badge / picker UIs.

    Used where the full member + repo lists would be wasted bandwidth
    (e.g. the BUD header's "assignee belongs to: <Team A>, <Team B>"
    badge).
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    status: TeamStatus


class TeamCreate(BaseModel):
    """Body for ``POST /v1/teams``."""

    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class TeamUpdate(BaseModel):
    """Body for ``PATCH /v1/teams/{team_id}``.

    Fields default to ``None`` and are skipped on the server. Use
    ``status='archived'`` to soft-delete a team — the row is kept so
    historical timeline events can still resolve its name.
    """

    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    status: TeamStatus | None = None


class TeamMembershipBody(BaseModel):
    """Body for ``POST /v1/teams/{team_id}/members``."""

    user_id: uuid.UUID


class TeamRepoBody(BaseModel):
    """Body for ``POST /v1/teams/{team_id}/repos``."""

    repo_id: uuid.UUID
