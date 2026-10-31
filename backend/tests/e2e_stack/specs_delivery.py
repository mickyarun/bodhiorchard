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

"""Request bodies of the ``/__e2e`` delivery routes: repos, PRs, QA cases, releases.

Field names are camelCase on the wire to match the TypeScript fixtures.
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class RepoSpec(_Wire):
    """A tracked repository, as setup or Settings → Code would add it."""

    name: str = Field(pattern=r"^[a-z0-9][a-z0-9._-]*$")


class SeededRepo(_Wire):
    """What the test needs about the repo afterwards."""

    id: uuid.UUID
    name: str


class PullRequestSpec(_Wire):
    """A PR on one impacted repo, as the GitHub webhook would have recorded it."""

    repo_id: uuid.UUID
    number: int = Field(ge=1)
    title: str
    state: Literal["open", "merged", "closed"] = "open"


class DeliverySpec(_Wire):
    """The repos a BUD touches and their PRs.

    ``repo_ids`` lists every impacted repo, with or without a PR. They are
    also confirmed for review, as picking them in the Code review tab does.
    """

    repo_ids: list[uuid.UUID] = Field(min_length=1)
    pull_requests: list[PullRequestSpec] = Field(default_factory=list)


class ManualCaseSpec(_Wire):
    """One manual test case, as the QA agent writes it (result pending)."""

    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,20}$")
    title: str


class ManualCasesSpec(_Wire):
    """The BUD's manual test cases, replacing any it has."""

    cases: list[ManualCaseSpec] = Field(min_length=1)


class ReleaseSpec(_Wire):
    """A release PR merged into a stage's branch, as release detection records it."""

    stage: Literal["uat", "prod"]
    repo_id: uuid.UUID
    pr_number: int = Field(ge=1)
    title: str
