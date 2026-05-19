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

"""Static cross-checks between AGENT_SKILL_MAP, AgentType, and BUD_STAGE_AGENT_TYPE.

If any of these drift (e.g. a new agent name is added to the routing
map but not to the ``AgentType`` enum), the seed flow will silently
skip rows and ``resolve_skill_for_agent`` will return None. Fail fast
in tests instead.
"""

from __future__ import annotations

from app.agents.skill_mapping import (
    AGENT_SKILL_MAP,
    BUD_STAGE_AGENT_TYPE,
    SECTION_SKILL_MAP,
)
from app.models.agent_skill import AgentType
from app.models.bud import BUDStatus


def test_every_agent_skill_map_key_is_a_known_agent_type() -> None:
    """The seed iterates AGENT_SKILL_MAP and casts each key to AgentType."""
    valid_values = {at.value for at in AgentType}
    for agent_name in AGENT_SKILL_MAP:
        assert agent_name in valid_values, (
            f"AGENT_SKILL_MAP key {agent_name!r} has no matching AgentType enum value"
        )


def test_every_agent_type_has_a_seed_slug() -> None:
    """Every AgentType must appear in AGENT_SKILL_MAP so seeding covers it."""
    for at in AgentType:
        assert at.value in AGENT_SKILL_MAP, (
            f"AgentType.{at.name} has no slug in AGENT_SKILL_MAP — seed will not "
            f"create a row for it and resolve_skill_for_agent will return None"
        )


def test_bud_stage_agent_type_keys_are_valid_statuses() -> None:
    """BUD_STAGE_AGENT_TYPE must key off real BUDStatus values."""
    for stage in BUD_STAGE_AGENT_TYPE:
        assert isinstance(stage, BUDStatus)


def test_bud_stage_agent_types_have_seeds() -> None:
    """Each stage's agent_type must have a seed (so the dropdown is non-empty)."""
    for stage, agent_type in BUD_STAGE_AGENT_TYPE.items():
        assert agent_type.value in AGENT_SKILL_MAP, (
            f"Stage {stage.value} maps to agent_type {agent_type.value} which has "
            f"no seed slug — the create-BUD Advanced Settings dropdown for this "
            f"stage would be empty"
        )


def test_section_skill_map_slugs_match_agent_skill_map() -> None:
    """SECTION_SKILL_MAP slugs must appear in AGENT_SKILL_MAP's value set."""
    seed_slugs = set(AGENT_SKILL_MAP.values())
    for section, slug in SECTION_SKILL_MAP.items():
        assert slug in seed_slugs, (
            f"SECTION_SKILL_MAP[{section!r}] = {slug!r} but that slug is not "
            f"seeded by AGENT_SKILL_MAP — chat for this section will fail"
        )
