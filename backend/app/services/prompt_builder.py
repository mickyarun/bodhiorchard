"""Prompt builder for FlowDev agent execution.

Combines a skill definition, backlog item context, org knowledge, and repo
information into a complete prompt for Claude Code CLI execution.
"""

import structlog

from app.services.skill_loader import load_skill

logger = structlog.get_logger(__name__)


async def build_agent_prompt(
    backlog_item: dict,
    skill_name: str,
    repo_context: dict | None = None,
    org_knowledge: list[str] | None = None,
) -> str:
    """Build the full prompt to pass to Claude Code CLI.

    Output structure:
    1. Skill instructions (from markdown file)
    2. Context section: backlog item details
    3. Knowledge section: relevant org knowledge (from pgvector search)
    4. Repository section: which repo, branch, files to focus on
    5. Output format: what deliverable to produce

    Args:
        backlog_item: Dict with title, description, acceptance_criteria, priority.
        skill_name: The skill file to load (e.g., 'product-manager').
        repo_context: Optional dict with repo_name, branch, relevant_files.
        org_knowledge: Optional list of relevant knowledge snippets.

    Returns:
        Complete prompt string for Claude Code.
    """
    skill = load_skill(skill_name)

    sections: list[str] = []

    # 1. Skill instructions
    sections.append(skill.prompt)

    # 2. Backlog item context
    sections.append("---\n\n## Task Context\n")
    sections.append(f"**Title:** {backlog_item.get('title', 'Untitled')}")
    if backlog_item.get("description"):
        sections.append(f"\n**Description:**\n{backlog_item['description']}")
    if backlog_item.get("acceptance_criteria"):
        sections.append(f"\n**Acceptance Criteria:**\n{backlog_item['acceptance_criteria']}")
    if backlog_item.get("priority"):
        sections.append(f"\n**Priority:** {backlog_item['priority']}")

    # 3. Knowledge context
    if org_knowledge:
        sections.append("\n---\n\n## Organizational Knowledge\n")
        for i, item in enumerate(org_knowledge, 1):
            sections.append(f"{i}. {item}")

    # 4. Repository context
    if repo_context:
        sections.append("\n---\n\n## Repository Context\n")
        if repo_context.get("repo_name"):
            sections.append(f"**Repository:** {repo_context['repo_name']}")
        if repo_context.get("branch"):
            sections.append(f"**Branch:** {repo_context['branch']}")
        if repo_context.get("relevant_files"):
            files = repo_context["relevant_files"]
            sections.append("**Relevant Files:**\n" + "\n".join(f"- `{f}`" for f in files))

    # 5. Deliverable instructions
    sections.append("\n---\n\n## Instructions\n")
    sections.append(
        "Complete the task described above. Use the available MCP tools to read context "
        "and write results back to FlowDev. Update your task status when done."
    )

    prompt = "\n".join(sections)

    logger.info(
        "prompt_built",
        skill=skill_name,
        backlog_title=backlog_item.get("title", ""),
        prompt_length=len(prompt),
        has_knowledge=bool(org_knowledge),
        has_repo_context=bool(repo_context),
    )

    return prompt
