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

"""Mapping from Bodhiorchard agent names to skill definition files.

Each Bodhiorchard agent (triage, bud, status, etc.) maps to a skill markdown
file in backend/app/agents/skills/ that defines its persona, tools, and workflow.
"""

AGENT_SKILL_MAP: dict[str, str] = {
    "triage": "triage-analyst",
    "bud": "product-manager",
    "status": "devops",
    "standup": "product-manager",
    "learning": "technical-writer",
    "bugLinker": "testing",
    "reassignment": "product-manager",
    "skill": "code-reviewer",
    "techPlan": "tech-planner",
    "testPlan": "testing",
    "design": "designer",
    "slackTriage": "slack-triage",
}

# Maps BUD section keys to the skill that handles chat for that section.
# Used by the chat job handler to read skill-level config (e.g. max_turns).
SECTION_SKILL_MAP: dict[str, str] = {
    "requirements_md": "product-manager",
    "tech_spec_md": "tech-planner",
    "test_plan_md": "testing",
    "design": "designer",
}


def get_skill_for_agent(agent_name: str) -> str | None:
    """Look up the skill name for a given Bodhiorchard agent.

    Args:
        agent_name: The agent key (e.g., 'triage', 'bud').

    Returns:
        The skill filename (without .md) or None if no mapping exists.
    """
    return AGENT_SKILL_MAP.get(agent_name)
