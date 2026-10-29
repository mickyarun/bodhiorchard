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

"""Request and response bodies of the ``/__e2e`` routes.

An org is seeded first (members, roles, reporting lines, leave types); the
content an area needs (registry features, an open quiz) is added to it with
its own call, so a new area adds a route instead of growing one spec. Field
names are camelCase on the wire to match the TypeScript fixtures.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class _Wire(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class MemberSpec(_Wire):
    """One person in the seeded org."""

    key: str = Field(pattern=r"^[a-z][a-z0-9_]*$")
    role: str | None = "developer"
    name: str | None = None
    manager: str | None = None
    must_change_password: bool = False
    # Engineers without an avatar are sent to the character picker after login.
    character_model: str | None = "barbarian"


class LeaveTypeSpec(_Wire):
    """A leave type on the org's default policy."""

    name: str
    code: str
    quota_days: Decimal = Decimal("10")


class FeatureSpec(_Wire):
    """A feature in the registry, as a scan would have written it."""

    title: str
    description: str
    tags: list[str] = Field(default_factory=list)


class FeaturesSpec(_Wire):
    """Features to add to an org's registry."""

    features: list[FeatureSpec] = Field(min_length=1)


class QuizSpec(_Wire):
    """A multiple-choice question, live as today's quiz."""

    prompt: str
    choices: list[str] = Field(min_length=2)
    correct_index: int = Field(ge=0)
    explanation: str = ""


class OrgSpec(_Wire):
    """An org and its people; content is added by the per-area routes."""

    password: str = Field(min_length=8)
    members: list[MemberSpec]
    # Seed into the oldest org (the one the login page signs in to) instead
    # of a new one. The login spec needs this; everything else gets its own org.
    # Leave types are skipped there: the org is shared.
    primary: bool = False
    quiz: bool = False
    leave_types: list[LeaveTypeSpec] = Field(
        default_factory=lambda: [LeaveTypeSpec(name="Casual leave", code="CL")]
    )


class SeededMember(_Wire):
    """A member the test can sign in as.

    The tokens are what the login API would hand back, so a test that isn't
    about logging in skips a round trip and a password hash check.
    """

    id: uuid.UUID
    email: str
    name: str
    access_token: str
    refresh_token: str


class SeededOrg(_Wire):
    """Ids and credentials the test uses afterwards."""

    id: uuid.UUID
    slug: str
    name: str
    members: dict[str, SeededMember]
    leave_types: dict[str, uuid.UUID]


class GuardReport(_Wire):
    """What the fakes refused while serving one test (or no test at all)."""

    violations: list[str]
    # Agent CLI runs the real ``claude`` would have rejected, or that no
    # script answered (see FakeClaudeRunner.assert_all_scripted).
    agent_problems: list[str]


class Identity(_Wire):
    """Which checkout this server runs from, so a reused stack can be checked."""

    repo_root: str
