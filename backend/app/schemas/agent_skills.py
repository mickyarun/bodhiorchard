# SPDX-License-Identifier: AGPL-3.0-or-later
# Copyright (C) 2026 Arun Rajkumar

"""Pydantic schemas for agent skill override endpoints."""

from pydantic import BaseModel, Field, model_validator

from app.services.skill_loader import Skill


class AgentSkillRead(BaseModel):
    """Schema for reading an agent skill (merged file default + DB override)."""

    skill_slug: str
    name: str
    description: str
    tools: list[str]
    mcp_tools: list[str]
    prompt: str
    max_turns: int = Field(0, description="Max Claude CLI turns (0 = unlimited)")
    model: str = Field("", description="Claude model alias or ID (empty = CLI default)")
    effort: str = Field(
        "", description="Reasoning effort: low, medium, high, max (empty = default)"
    )
    is_customized: bool = Field(
        False, description="True if a DB override exists (vs file default)"
    )

    model_config = {"from_attributes": True}

    @classmethod
    def from_skill(
        cls, slug: str, skill: Skill, *, is_customized: bool = False
    ) -> "AgentSkillRead":
        """Construct from a Skill dataclass to avoid scattered field mapping."""
        return cls(
            skill_slug=slug,
            name=skill.name,
            description=skill.description,
            tools=skill.tools,
            mcp_tools=skill.mcp_tools,
            prompt=skill.prompt,
            max_turns=skill.max_turns,
            model=skill.model,
            effort=skill.effort,
            is_customized=is_customized,
        )


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
    model: str | None = Field(None, max_length=100, description="Claude model alias or ID")
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
                self.model,
                self.effort,
            )
        ):
            raise ValueError("At least one field must be provided")
        return self
