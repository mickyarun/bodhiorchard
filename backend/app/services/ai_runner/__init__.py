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

"""Pluggable AI provider seam.

``run_agent`` is the single entry point for backend agent runs: it resolves
the org's provider (Claude / Copilot / Codex) and delegates to it. The
config/result types are reused from ``claude_runner`` so call sites and
result handlers are provider-agnostic.
"""

import uuid
from pathlib import Path

import structlog

from app.database import AsyncSessionLocal
from app.models.organization import AIProvider, Organization
from app.repositories.organization import OrganizationRepository
from app.services.ai_runner.base import AgentProvider
from app.services.ai_runner.claude_provider import ClaudeProvider
from app.services.ai_runner.registry import provider_for
from app.services.claude_runner import (
    ClaudeRunnerConfig,
    ClaudeRunResult,
    ProgressCallback,
)

logger = structlog.get_logger(__name__)

__all__ = [
    "AgentProvider",
    "ClaudeProvider",
    "provider_for",
    "run_agent",
    "run_agent_for_org_id",
]


async def run_agent(
    org: Organization | None,
    prompt: str,
    working_dir: str | Path,
    config: ClaudeRunnerConfig | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ClaudeRunResult:
    """Run ``prompt`` through the agent provider configured for ``org``.

    Drop-in for direct ``run_claude_code`` calls, with the provider chosen
    per-org via :func:`provider_for`.
    """
    provider = provider_for(org)
    cfg = config or ClaudeRunnerConfig()
    logger.info(
        "agent_run",
        provider=(org.ai_provider if org is not None else AIProvider.claude).value,
        requested_model=cfg.model or "(cli default)",
        requested_effort=cfg.effort or "(cli default)",
    )
    return await provider.run(prompt, working_dir, cfg, progress_callback)


async def run_agent_for_org_id(
    org_id: uuid.UUID | None,
    prompt: str,
    working_dir: str | Path,
    config: ClaudeRunnerConfig | None = None,
    progress_callback: ProgressCallback | None = None,
) -> ClaudeRunResult:
    """``run_agent`` for callers that hold only an ``org_id``.

    Loads the ``Organization`` (a single PK lookup on its own session) so
    the run routes through the org's provider. A ``None`` org_id (or an
    org that can't be found) falls back to Claude via :func:`run_agent`.
    """
    org = None
    if org_id is not None:
        async with AsyncSessionLocal() as db:
            org = await OrganizationRepository(db).get_by_id(org_id)
    return await run_agent(org, prompt, working_dir, config, progress_callback)
