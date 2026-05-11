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

"""Pydantic schemas for the Standup API."""

from datetime import date, datetime

from pydantic import BaseModel, Field


class BUDTransition(BaseModel):
    """A single BUD stage transition within the standup window."""

    bud_number: int
    title: str
    from_stage: str
    to_stage: str


class StandupFlag(BaseModel):
    """A risk flag detected during standup generation."""

    type: str = Field(description="no_activity | bud_lagging | critical_bugs | bus_factor")
    severity: str = Field(description="info | warning | critical")
    description: str
    bud_number: int | None = None
    user_id: str | None = None
    user_name: str | None = None


class MemberStandupItem(BaseModel):
    """Per-member activity summary within the standup window."""

    user_id: str
    name: str
    avatar_url: str | None = None
    level: int = 1
    level_name: str = "seedling"

    commits_count: int = 0
    files_changed: int = 0
    prs_opened: int = 0
    prs_merged: int = 0
    buds_transitioned: list[BUDTransition] = Field(default_factory=list)
    bugs_filed: int = 0
    bugs_resolved: int = 0
    xp_earned: int = 0
    agent_tasks_completed: int = 0

    flags: list[StandupFlag] = Field(default_factory=list)


class StandupReportRead(BaseModel):
    """Full standup report response."""

    id: str
    date: date
    members: list[MemberStandupItem] = Field(default_factory=list)
    flags: list[StandupFlag] = Field(default_factory=list)
    summary: str | None = None
    since_timestamp: str | None = Field(
        default=None,
        description="ISO timestamp of the time window start",
    )
    created_at: datetime

    model_config = {"from_attributes": True}


class StandupReportListItem(BaseModel):
    """Minimal standup entry for list endpoint."""

    id: str
    date: date
    member_count: int = 0
    flag_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}
