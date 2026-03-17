"""Mapping from FlowDev agent names to skill definition files.

Each FlowDev agent (triage, prd, status, etc.) maps to a skill markdown
file in backend/app/agents/skills/ that defines its persona, tools, and workflow.
"""

AGENT_SKILL_MAP: dict[str, str] = {
    "triage": "triage-analyst",
    "prd": "product-manager",
    "status": "devops",
    "standup": "product-manager",
    "learning": "technical-writer",
    "bugLinker": "qa-engineer",
    "reassignment": "product-manager",
    "skill": "code-reviewer",
    "techPlan": "tech-planner",
    "testPlan": "test-planner",
    "design": "designer",
}


def get_skill_for_agent(agent_name: str) -> str | None:
    """Look up the skill name for a given FlowDev agent.

    Args:
        agent_name: The agent key (e.g., 'triage', 'prd').

    Returns:
        The skill filename (without .md) or None if no mapping exists.
    """
    return AGENT_SKILL_MAP.get(agent_name)
