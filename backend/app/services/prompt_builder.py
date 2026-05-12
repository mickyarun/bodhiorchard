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

"""Prompt builder for Bodhiorchard agent execution.

Combines a skill definition, backlog item context, org knowledge, and repo
information into a complete prompt for Claude Code CLI execution.
"""

import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.skill_loader import Skill, load_skill, load_skill_for_org

logger = structlog.get_logger(__name__)


async def _resolve_skill(
    skill_name: str,
    org_id: uuid.UUID | None,
    db: AsyncSession | None,
) -> Skill:
    """Load a skill, preferring DB override when org context is provided.

    Args:
        skill_name: The skill slug (e.g. 'product-manager').
        org_id: Organization UUID. Must be paired with db.
        db: Async database session. Must be paired with org_id.

    Returns:
        A Skill object.

    Raises:
        ValueError: If only one of org_id/db is provided (programming error).
    """
    if (org_id is None) != (db is None):
        raise ValueError(
            "Both org_id and db must be provided together, or neither. "
            f"Got org_id={org_id!r}, db={'present' if db else None}"
        )
    if org_id is not None and db is not None:
        return await load_skill_for_org(skill_name, org_id, db)
    return load_skill(skill_name)


async def build_agent_prompt(
    backlog_item: dict[str, Any],
    skill_name: str,
    repo_context: dict[str, Any] | None = None,
    org_knowledge: list[str] | None = None,
    *,
    org_id: uuid.UUID | None = None,
    db: AsyncSession | None = None,
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
    skill = await _resolve_skill(skill_name, org_id, db)

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
        "and write results back to Bodhiorchard. Update your task status when done."
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


async def build_slack_triage_prompt(
    skill_name: str,
    session_status: str,
    original_text: str,
    thread_messages: list[dict[str, Any]],
    *,
    triage_context: dict[str, Any] | None = None,
    org_id: uuid.UUID | None = None,
    db: AsyncSession | None = None,
) -> str:
    """Build a prompt for the Slack triage agent using thread history.

    Instead of a backlog item, provides the Slack thread conversation
    so the agent can continue an interactive triage interview.

    Args:
        skill_name: The skill file to load (e.g., 'slack-triage').
        session_status: Current TriageSession status for state awareness.
        original_text: The original Slack message that triggered the triage.
        thread_messages: List of Slack message dicts from conversations.replies.
        triage_context: Accumulated context from previous interview turns.

    Returns:
        Complete prompt string for the triage agent.
    """
    skill = await _resolve_skill(skill_name, org_id, db)

    sections: list[str] = []

    # 1. Skill instructions
    sections.append(skill.prompt)

    # 2. Session state
    sections.append("---\n\n## Triage Session State\n")
    sections.append(f"**Status:** {session_status}")
    if triage_context:
        sections.append(f"**Accumulated context:** {triage_context}")

    # 3. Thread history (truncate to last 15 messages + original)
    sections.append("\n---\n\n## Conversation Thread\n")
    messages = thread_messages[-15:] if len(thread_messages) > 15 else thread_messages
    for msg in messages:
        user = msg.get("user", "unknown")
        text = msg.get("text", "")
        is_bot = bool(msg.get("bot_id"))
        ts = msg.get("ts", "")

        if ts == thread_messages[0].get("ts", ""):
            prefix = "[ORIGINAL]"
        elif is_bot:
            prefix = "[BOT]"
        else:
            prefix = "[REPLY]"

        sections.append(f"{prefix} {user}: {text}")

    # 4. Instructions
    sections.append("\n---\n\n## Instructions\n")
    if session_status == "interviewing":
        sections.append(
            "Review the conversation so far. If you have enough context to assess "
            "this feature request, you MUST call `check_feature_exists` with the "
            "feature description before producing a summary. Do NOT skip this step. "
            "If you do not yet have enough context, ask a focused follow-up question."
        )
    elif session_status == "checking":
        sections.append(
            "You are checking for existing features. Use check_feature_exists with "
            "the feature description and report findings."
        )
    else:
        sections.append("Continue the triage conversation based on the current state.")

    prompt = "\n".join(sections)

    logger.info(
        "slack_triage_prompt_built",
        skill=skill_name,
        session_status=session_status,
        thread_length=len(messages),
        prompt_length=len(prompt),
    )

    return prompt


async def build_prd_prompt(
    skill_name: str,
    bud_number: int,
    bud_title: str,
    triage_context: dict[str, Any],
    requirements_md: str,
    *,
    org_id: uuid.UUID | None = None,
    db: AsyncSession | None = None,
    repo_summaries: list[str] | None = None,
    candidate_features: list[tuple[str, str, float]] | None = None,
) -> str:
    """Build a prompt for the Product Manager agent to enrich a BUD with a full PRD.

    Args:
        skill_name: The skill file to load (e.g., 'product-manager').
        bud_number: The BUD number to reference.
        bud_title: The BUD title.
        triage_context: Accumulated context from the triage interview.
        requirements_md: The initial BUD content from triage.
        org_id: Organization UUID — required for DB-backed skill override.
        db: Async database session — required for DB-backed skill override.
        repo_summaries: Optional one-line repo descriptors (``"- **name**
            — layer=…"``) used to ground the PM in the real tracked
            repositories. Renders as a "Tracked Repositories" section.
        candidate_features: Optional ``(feature_id_str, title,
            similarity)`` tuples from a semantic prefetch over existing
            features. Renders as "Possibly-related existing features".

    Returns:
        Complete prompt string for the PM agent.
    """
    skill = await _resolve_skill(skill_name, org_id, db)

    sections: list[str] = []

    # 1. Skill instructions
    sections.append(skill.prompt)

    # 2. BUD context
    bud_ref = f"BUD-{bud_number:03d}"
    sections.append("---\n\n## Task Context\n")
    sections.append(f"**BUD:** {bud_ref}")
    sections.append(f"**Title:** {bud_title}")
    sections.append(f"\n**Triage Context:**\n```json\n{triage_context}\n```")
    sections.append(f"\n**Current Content:**\n{requirements_md}")

    # 3. Grounding context — repos + likely-related existing features.
    # Both sections are short, deterministic, and override the LLM's
    # tendency to invent product names ("bodhigrove" etc.) or duplicate
    # existing features when it has zero prior context.
    if repo_summaries:
        sections.append("\n---\n\n## Tracked Repositories\n")
        sections.extend(repo_summaries)
        sections.append(
            "\n_All claims in this PRD must be grounded in these repos. "
            "Do NOT invent product names or repos._"
        )
    if candidate_features:
        sections.append("\n---\n\n## Possibly-related existing features\n")
        sections.append(
            "_Top matches by semantic similarity to the brief above — "
            "treat as suggestions. If you need more, call "
            '`get_features(query="...")`._\n'
        )
        for feature_id, title, similarity in candidate_features:
            sections.append(f"- `{feature_id}` — {title} (similarity {similarity:.2f})")

    # 4. Instructions
    sections.append("\n---\n\n## Instructions\n")
    sections.append(
        f"Enrich {bud_ref} with a focused PRD. Use `get_bud_context` to "
        "read the current BUD, then `get_features` to search for related "
        f"features (refine the query if the prefetch above misses). Write "
        f"back using `write_bud` with `bud_number: {bud_number}` to UPDATE.\n\n"
        "**IMPORTANT:** Pass `bud_number` to `write_bud` — omitting it creates a duplicate.\n\n"
        "**Keep it crisp — target 1,500-3,000 characters total.** "
        "Developers use Claude Code and need scope and decisions, not verbose explanations.\n\n"
        "Sections (strict format):\n"
        "- **Problem Statement**: 2-3 sentences. What's broken and why.\n"
        "- **Proposed Solution**: Bullet points. What to build, not how.\n"
        "- **Acceptance Criteria**: Checklist, one line each, max 8 items.\n"
        "- **Edge Cases**: Table (scenario | expected behavior), max 6 rows.\n"
        "- **Dependencies & Risks**: Bullet points, real blockers only.\n\n"
        "No code examples. No implementation details. No preamble.\n"
        "Preserve the existing triage origin — append sections below it.\n\n"
        "## Output Tail (REQUIRED)\n\n"
        "After calling `write_bud`, end your final message with EXACTLY one\n"
        "JSON fence listing the existing features your requirement touches —\n"
        "use the ids from the 'Possibly-related existing features' list above\n"
        "or from `get_features` results. Use an empty array when nothing applies.\n\n"
        "```json\n"
        '{"linked_feature_ids": ["<feature-uuid>", "..."]}\n'
        "```"
    )

    prompt = "\n".join(sections)

    logger.info(
        "prd_prompt_built",
        skill=skill_name,
        bud_number=bud_number,
        prompt_length=len(prompt),
        repo_count=len(repo_summaries or []),
        candidate_count=len(candidate_features or []),
    )

    return prompt
