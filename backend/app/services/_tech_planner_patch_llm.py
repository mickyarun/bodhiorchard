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

"""Claude subprocess wiring for :mod:`tech_planner_patch`.

Resolves the org-customised tech-planner skill row, composes the
patch-mode prompt, runs the CLI, and extracts the replacement section
from the response. Package-private — callers should use
:func:`app.services.tech_planner_patch.maybe_patch_todo_section`.
"""

import re
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bud import BUDDocument
from app.services.claude_runner import ClaudeRunnerConfig, run_claude_code
from app.services.skill_loader import Skill, load_skill, load_skill_for_org

logger = structlog.get_logger(__name__)

_SKILL_SLUG = "tech-planner"
_TIMEOUT_FALLBACK_SECONDS = 90
_AGENT_MAX_TURNS = 1
_PATCH_PROMPT_MARKER = "mode: patch_todo"


async def request_patched_section(
    *,
    bud: BUDDocument,
    old_spec: str,
    new_spec: str,
    db: AsyncSession,
    org_id: uuid.UUID,
) -> str | None:
    """Ask tech-planner for a replacement Implementation TODO section.

    Returns the section text on success, ``None`` on LLM failure or
    obviously-malformed output. Never raises — the caller treats
    ``None`` as "skip splice, the parser will work on the unchanged
    spec".
    """
    skill = await _resolve_skill(db, org_id)
    prompt = _build_prompt(skill, bud=bud, old_spec=old_spec, new_spec=new_spec)
    config = ClaudeRunnerConfig(
        max_turns=_AGENT_MAX_TURNS,
        timeout_seconds=skill.timeout_or_default(_TIMEOUT_FALLBACK_SECONDS),
        allowed_tools=[],
        model=skill.model or None,
        effort=skill.effort or None,
    )

    result = await run_claude_code(prompt=prompt, config=config)
    if not result.success or not result.output:
        logger.warning(
            "tech_planner_patch_failed",
            bud_id=str(bud.id),
            error=result.error,
        )
        return None

    section = extract_section(result.output)
    if section is None:
        logger.warning(
            "tech_planner_patch_malformed",
            bud_id=str(bud.id),
            output_preview=result.output[:200],
        )
        return None
    return section


async def _resolve_skill(db: AsyncSession, org_id: uuid.UUID) -> Skill:
    """Load the org-customised tech-planner row; fall back to file default."""
    try:
        return await load_skill_for_org(_SKILL_SLUG, org_id, db)
    except ValueError:
        return load_skill(_SKILL_SLUG)


def _build_prompt(
    skill: Skill,
    *,
    bud: BUDDocument,
    old_spec: str,
    new_spec: str,
) -> str:
    """Compose the patch-mode prompt: skill body + diff context + new spec."""
    return (
        f"{skill.prompt}\n\n"
        f"{_PATCH_PROMPT_MARKER}\n\n"
        "## Previous spec\n\n"
        f"{old_spec}\n\n"
        "## Updated spec (body changed; TODO section may now be stale)\n\n"
        f"{new_spec}\n\n"
        "Emit ONLY a replacement `## Implementation TODO` section as a "
        "single fenced markdown block. No preamble, no rewrites of any "
        "other section.\n"
    )


def extract_section(output: str) -> str | None:
    """Pull the Implementation TODO section out of the LLM response.

    The skill is told to emit a single fenced markdown block. We accept
    either a fenced block or bare markdown containing the header.
    """
    fenced = re.search(r"```(?:markdown|md)?\n(.*?)\n```", output, re.DOTALL)
    body = fenced.group(1).strip() if fenced else output.strip()
    if not re.search(r"^#{1,6}\s+implementation\s+todo", body, re.IGNORECASE | re.MULTILINE):
        return None
    return body
