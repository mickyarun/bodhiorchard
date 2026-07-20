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

"""Refuses runs a provider cannot actually perform, and adapts the rest.

Not every provider can do everything. Ollama has tools but no filesystem and
no session affinity, so a caller that hands it a repo path and a prompt saying
"read these files" gets a fluent answer about files it never opened — a
*plausible* result, which is worse than an error because nothing looks wrong.
Scan synthesis is the sharpest case: its output arrives entirely via MCP side
effects, so an incapable provider yields a clean, silent zero-feature scan.

So the capability table decides up front, and an unsupported combination fails
loudly here rather than being discovered downstream. This is a correctness
guard, not a security boundary — ``connection_check`` deliberately calls
providers directly and bypasses it.
"""

from dataclasses import replace
from pathlib import Path

import structlog

from app.models.organization import Organization
from app.services.ai_runner.capability_types import ProviderCapabilities
from app.services.ai_runner.ollama_models import (
    OLLAMA_HOST_ENV,
    OLLAMA_MODEL_ENV,
    OLLAMA_THINK_ENV,
    clean_base_url,
)
from app.services.claude_runner import NO_REPO_CONTEXT, ClaudeRunnerConfig

logger = structlog.get_logger(__name__)


def unsupported_reason(
    caps: ProviderCapabilities, working_dir: str | Path, config: ClaudeRunnerConfig
) -> str | None:
    """Why ``caps``' provider cannot run this, or None if it can.

    The message is user-facing: it says what is missing and what to do about
    it, because it surfaces in a job error where the reader is an operator,
    not the person who wrote this code.
    """
    name = caps.provider.value

    # A real working_dir means the caller expects the agent to read files.
    # Checked via the sentinel, NOT via max_turns: max_turns == 0 means
    # *unlimited* (claude_runner omits the flag when <= 0), so a "> 1" test
    # would read the most agentic callers as single-turn.
    if not caps.supports_files and str(working_dir) != NO_REPO_CONTEXT:
        return (
            f"This feature needs to read the repository, which the {name} provider "
            f"cannot do — it has no filesystem access. Switch the organisation to a "
            f"CLI-based provider (Settings → AI Config) to use it."
        )
    if not caps.supports_mcp and config.mcp is not None:
        return (
            f"This feature needs MCP tools, which the {name} provider cannot use. "
            f"Switch the organisation to a provider that supports them."
        )
    if not caps.supports_resume and config.is_resume:
        return (
            f"This feature resumes an earlier agent session, which the {name} "
            f"provider cannot do — its calls are stateless."
        )
    return None


def provider_env(
    caps: ProviderCapabilities,
    *,
    base_url: str | None,
    model: str | None,
    thinking: bool,
) -> dict[str, str]:
    """The per-run settings ``caps``' provider needs, as an env mapping.

    Takes loose values rather than an org, because both callers need this and
    only one of them has an org: a real run reads the org's saved settings, and
    the setup wizard has values the user has typed but not yet saved. Feeding
    both through here is what keeps "Test connection" honest — it checks the
    configuration the run will actually use, rather than a default that happens
    to work on the developer's machine.

    Returns ``{}`` for a provider with none of these, so callers can skip.

    The address is re-validated here rather than trusted from the caller. This
    is the one point every address passes through — the org's saved value and
    the wizard's unsaved one — and the wizard reaches it from an unauthenticated
    endpoint. A check that lives only in the settings handler leaves that path
    open, which is exactly what it did. An invalid address falls back to the
    provider default instead of raising: this function builds a run's
    environment and has no way to report a bad request, and a run against the
    default fails visibly rather than silently reaching somewhere it shouldn't.
    """
    env: dict[str, str] = {}
    if caps.requires_base_url:
        default = caps.default_base_url or ""
        try:
            safe = clean_base_url(base_url)
        except ValueError:
            logger.warning("provider_env_rejected_base_url", provider=caps.provider.value)
            safe = None
        env[OLLAMA_HOST_ENV] = safe or default
    if caps.supports_thinking:
        env[OLLAMA_THINK_ENV] = "1" if thinking else "0"
    if caps.dynamic_models and (model or "").strip():
        # The org's choice, from what its host actually has installed. A
        # skill's own `model` is a different provider's vocabulary ("sonnet",
        # "haiku") and would 404 against a local server.
        env[OLLAMA_MODEL_ENV] = (model or "").strip()
    return env


def adapt_config(
    caps: ProviderCapabilities, org: Organization | None, config: ClaudeRunnerConfig
) -> ClaudeRunnerConfig:
    """Reshape ``config`` for ``caps``' provider without touching call sites.

    Two jobs:

    1. Scale limits the caller chose for a hosted API. Local inference is far
       slower, and an unbounded tool loop on a small model is a real hazard,
       so the table's multiplier and turn cap are applied at this seam rather
       than at all ~19 call sites.
    2. Carry org-scoped settings down to the provider. Providers never receive
       the org — only ``config`` — and ``os.environ`` is process-global, so
       two orgs on different hosts would clobber each other there. ``env_extra``
       is per-run, which keeps it multi-tenant safe; it is also how
       ``connection_check`` already passes provisional wizard values, so the
       setup "test before save" path works through the same code.
    """
    changes: dict[str, object] = {}

    if caps.timeout_multiplier != 1.0:
        changes["timeout_seconds"] = int(config.timeout_seconds * caps.timeout_multiplier)
    if caps.max_turns_cap is not None:
        # max_turns <= 0 means unlimited, which a capped provider must not honour.
        capped = (
            caps.max_turns_cap
            if config.max_turns <= 0
            else min(config.max_turns, caps.max_turns_cap)
        )
        if capped != config.max_turns:
            changes["max_turns"] = capped

    # Only read the host settings for a provider that actually uses them — the
    # CLI providers don't, and touching an org's columns to build a mapping
    # that would come back empty is just a way to fail on something unrelated.
    if caps.requires_base_url or caps.supports_thinking or caps.dynamic_models:
        provider_settings = provider_env(
            caps,
            base_url=org.ai_base_url if org else None,
            model=org.ai_model if org else None,
            thinking=bool(org.ai_thinking) if org else False,
        )
        if provider_settings:
            changes["env_extra"] = {**(config.env_extra or {}), **provider_settings}

    if not changes:
        return config
    adapted = replace(config, **changes)  # type: ignore[arg-type]
    logger.debug(
        "ai_config_adapted",
        provider=caps.provider.value,
        timeout_seconds=adapted.timeout_seconds,
        max_turns=adapted.max_turns,
    )
    return adapted
