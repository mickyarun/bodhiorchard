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

"""Pydantic schemas for agent skill override endpoints."""

import uuid

from pydantic import BaseModel, Field, model_validator

from app.models.agent_skill import AgentType
from app.services.skill_loader import Skill


class AgentSkillRead(BaseModel):
    """Schema for reading an agent skill row (seeded or custom)."""

    id: uuid.UUID | None = None
    skill_slug: str
    agent_type: AgentType
    is_default: bool = False
    is_custom: bool = False
    name: str
    description: str
    tools: list[str]
    mcp_tools: list[str]
    prompt: str
    max_turns: int = Field(0, description="Max Claude CLI turns (0 = unlimited)")
    timeout_seconds: int = Field(
        0,
        description="Wall-clock cap in seconds for the Claude call (0 = use agent's fallback)",
    )
    model: str = Field("", description="Claude model alias or ID (empty = CLI default)")
    iteration_model: str = Field(
        "",
        description=(
            "Optional faster model for chat-iteration paths "
            "(e.g. claude-haiku-4-5). Empty falls back to ``model``."
        ),
    )
    effort: str = Field(
        "", description="Reasoning effort: low, medium, high, max (empty = default)"
    )
    is_customized: bool = Field(
        False, description="True if a DB override exists (vs file default)"
    )

    model_config = {"from_attributes": True}

    @classmethod
    def from_skill(
        cls,
        slug: str,
        skill: Skill,
        *,
        agent_type: AgentType,
        is_customized: bool = False,
    ) -> "AgentSkillRead":
        """Construct from a Skill dataclass to avoid scattered field mapping."""
        return cls(
            skill_slug=slug,
            agent_type=agent_type,
            name=skill.name,
            description=skill.description,
            tools=skill.tools,
            mcp_tools=skill.mcp_tools,
            prompt=skill.prompt,
            max_turns=skill.max_turns,
            timeout_seconds=skill.timeout_seconds,
            model=skill.model,
            iteration_model=skill.iteration_model,
            effort=skill.effort,
            is_customized=is_customized,
        )


class CustomSkillCreate(BaseModel):
    """Schema for adding a user-authored custom skill."""

    name: str = Field(..., min_length=1, max_length=255)
    agent_type: AgentType
    skill_slug: str = Field(
        ...,
        min_length=1,
        max_length=100,
        pattern=r"^[a-z0-9][a-z0-9-]*$",
        description="kebab-case identifier; must be unique within (org, agent_type)",
    )
    description: str = Field("", max_length=5000)
    prompt: str = Field(..., min_length=1, max_length=100_000)
    tools: list[str] = Field(default_factory=list)
    mcp_tools: list[str] = Field(default_factory=list)
    max_turns: int = Field(0, ge=0, le=100)
    timeout_seconds: int = Field(0, ge=0, le=3600)
    model: str = Field("", max_length=100)
    iteration_model: str = Field("", max_length=100)
    effort: str = Field("", max_length=20)


class AgentSkillUpdate(BaseModel):
    """Schema for creating or updating a skill override.

    At least one field must be provided.
    """

    name: str | None = Field(None, min_length=1, max_length=255)
    description: str | None = Field(None, max_length=5000)
    tools: list[str] | None = None
    mcp_tools: list[str] | None = None
    prompt: str | None = Field(None, min_length=1, max_length=100_000)
    max_turns: int | None = Field(None, ge=0, le=100, description="0 = unlimited")
    timeout_seconds: int | None = Field(
        None,
        ge=0,
        le=3600,
        description="Wall-clock cap in seconds; 0 = use code-side fallback. Max 1 hour.",
    )
    model: str | None = Field(None, max_length=100, description="Claude model alias or ID")
    iteration_model: str | None = Field(
        None, max_length=100, description="Faster model for chat iteration (empty = use model)"
    )
    effort: str | None = Field(None, max_length=20, description="Reasoning effort level")

    @model_validator(mode="after")
    def check_at_least_one_field(self) -> "AgentSkillUpdate":
        """Reject completely empty payloads."""
        if all(
            v is None
            for v in (
                self.name,
                self.description,
                self.tools,
                self.mcp_tools,
                self.prompt,
                self.max_turns,
                self.timeout_seconds,
                self.model,
                self.iteration_model,
                self.effort,
            )
        ):
            raise ValueError("At least one field must be provided")
        return self
