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

"""Single-shot retry for BUD-agent spawns hit by git/GitHub auth failure.

Pulled out of :mod:`app.services.bud_agent_handler` so the orchestration
function stays under the project's file-size target and the retry logic
gets its own focused unit tests. The contract:

* Only retries when the first spawn *succeeded* but its output carries
  a git/GitHub auth rejection (see
  :func:`app.services.agent_result_handlers.is_git_auth_failure`).
* Invalidates the cached installation token, re-stamps ``origin`` with
  a freshly-minted one, and spawns once more with a NEW CLI session id
  so the retry never resumes a session that may have already triggered
  partial MCP side-effects.
* Records an ``agent_retried`` activity row so the BUD timeline shows
  both spawns and downstream cost/turn accounting reconciles.
"""

import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_activity_logger import log_agent_activity
from app.services.agent_result_handlers import is_git_auth_failure
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    ClaudeRunResult,
    ProgressCallback,
    run_claude_code,
)
from app.services.github_app_auth import invalidate_installation_token
from app.services.github_remote_refresh import refresh_origin_token
from app.services.section_session import mint_session_id

logger = structlog.get_logger(__name__)


async def maybe_retry_on_git_auth_failure(
    *,
    result: ClaudeRunResult,
    prompt: str,
    spawn_cwd: str,
    working_dir: str | None,
    config: ClaudeRunnerConfig,
    progress_callback: ProgressCallback | None,
    org_id: uuid.UUID,
    bud_id: uuid.UUID,
    task_id: uuid.UUID,
    skill_id: uuid.UUID | None,
    skill_slug: str,
    repo_id: uuid.UUID | None,
    db: AsyncSession,
) -> ClaudeRunResult:
    """Re-spawn once if ``result.output`` shows an auth rejection.

    Returns the original ``result`` unchanged when no retry is
    warranted. Returns the second-spawn result otherwise. Never raises:
    every failure mode of the retry path is logged and folded back into
    a ``ClaudeRunResult`` for the caller to handle uniformly.
    """
    if not working_dir:
        # Pure-LLM call (no repo context) cannot legitimately emit a
        # git auth failure — anything matching the regex would be
        # incidental text from the model. Skip.
        return result
    if not result.success:
        # Crash already; the caller will record FAILED. Mixing the
        # retry with crash recovery would mask real bugs as flaky auth.
        return result
    if not is_git_auth_failure(result.output or ""):
        return result

    logger.warning(
        "bud_agent_git_auth_retry",
        task_id=str(task_id),
        bud_id=str(bud_id),
        skill_slug=skill_slug,
    )

    invalidate_installation_token(str(org_id))
    await refresh_origin_token(
        working_dir=working_dir,
        org_id=org_id,
        db=db,
    )

    # Fresh session id on the retry. Resuming the original session would
    # replay any MCP tool calls the first spawn fired before hitting the
    # auth wall, producing duplicate ``write_bud`` rows / double-counted
    # comments. A clean session forces the CLI to start over.
    retry_config = ClaudeRunnerConfig(
        max_turns=config.max_turns,
        timeout_seconds=config.timeout_seconds,
        output_format=config.output_format,
        mcp=config.mcp,
        system_prompt_files=list(config.system_prompt_files),
        model=config.model,
        effort=config.effort,
        env_extra=dict(config.env_extra) if config.env_extra else None,
        cli_session_id=str(mint_session_id()),
        is_resume=False,
        allowed_tools=list(config.allowed_tools),
    )

    await log_agent_activity(
        db,
        org_id=org_id,
        event_type="agent_retried",
        skill_slug=skill_slug,
        message=f"Auth-failure retry for '{skill_slug}'",
        bud_id=bud_id,
        skill_id=skill_id,
        task_id=task_id,
        repo_id=repo_id,
    )

    return await run_claude_code(
        prompt=prompt,
        working_dir=spawn_cwd,
        config=retry_config,
        progress_callback=progress_callback,
    )
