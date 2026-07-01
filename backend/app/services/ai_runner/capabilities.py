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

"""Per-provider capability table — the single source of truth.

Both the backend (auth dispatch, connection test, model resolution) and the
frontend (provider selector + Agent Prompts dropdowns, via an API endpoint)
read this table, so the UI can never offer a setting an adapter would reject.
Adding a provider is one entry here, not edits across five files.

Model ids / effort levels are best-effort as of 2026-06 and verified against
the installed CLIs where possible; ``resolve_model`` degrades unknown values
to the provider default, so a stale id is safe (logged), never fatal.
"""

from dataclasses import dataclass

import structlog

from app.models.organization import AIProvider

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ModelChoice:
    """A selectable model for a provider (UI label + CLI id)."""

    id: str
    label: str


@dataclass(frozen=True)
class AuthModeSpec:
    """An auth mode a provider supports and the env var(s) it sets.

    ``requires_secret`` modes store an encrypted credential on the org;
    ``host`` modes inherit credentials from the process / CLI login.
    """

    value: str
    label: str
    requires_secret: bool
    env_vars: tuple[str, ...]


@dataclass(frozen=True)
class ProviderCapabilities:
    """Everything the UI and backend need to drive one provider."""

    provider: AIProvider
    cli: str
    models: tuple[ModelChoice, ...]
    default_model: str
    supports_effort: bool
    effort_values: tuple[str, ...]
    supports_iteration_model: bool
    auth_modes: tuple[AuthModeSpec, ...]
    version_cmd: tuple[str, ...]
    install_hint: str
    docs_url: str


# Host mode sets nothing, but its env_vars name the host/compose-owned
# credentials the auth dispatcher must PRESERVE (not clear) in host mode.
_HOST_CLAUDE = AuthModeSpec("host", "Hybrid / host login", False, ("ANTHROPIC_API_KEY",))
_API_KEY_CLAUDE = AuthModeSpec("api_key", "Anthropic API key", True, ("ANTHROPIC_API_KEY",))
_SUBSCRIPTION_CLAUDE = AuthModeSpec(
    "subscription", "Claude subscription token", True, ("CLAUDE_CODE_OAUTH_TOKEN",)
)
# Host mode preserves the host's GH_TOKEN; token mode sets only the dedicated
# COPILOT_GITHUB_TOKEN (highest precedence) so it never clobbers the host's
# GH_TOKEN used for git operations.
_HOST_COPILOT = AuthModeSpec("host", "Host gh / Copilot login", False, ("GH_TOKEN",))
_TOKEN_COPILOT = AuthModeSpec("api_key", "GitHub token", True, ("COPILOT_GITHUB_TOKEN",))
_HOST_CODEX = AuthModeSpec("host", "Host Codex login", False, ())
_API_KEY_CODEX = AuthModeSpec("api_key", "OpenAI API key", True, ("OPENAI_API_KEY",))


CAPABILITIES: dict[AIProvider, ProviderCapabilities] = {
    AIProvider.claude: ProviderCapabilities(
        provider=AIProvider.claude,
        cli="claude",
        models=(
            ModelChoice("", "Default"),
            ModelChoice("sonnet", "Balanced (Sonnet)"),
            ModelChoice("opus", "Deep (Opus)"),
            ModelChoice("haiku", "Fast (Haiku)"),
        ),
        default_model="",
        supports_effort=True,
        effort_values=("low", "medium", "high", "max"),
        supports_iteration_model=True,
        auth_modes=(_HOST_CLAUDE, _API_KEY_CLAUDE, _SUBSCRIPTION_CLAUDE),
        version_cmd=("claude", "--version"),
        install_hint="Install: curl -fsSL https://claude.ai/install.sh | bash",
        docs_url="https://docs.claude.com/en/docs/claude-code",
    ),
    AIProvider.copilot: ProviderCapabilities(
        provider=AIProvider.copilot,
        cli="copilot",
        # Explicit --model ids are account/plan-gated (most reject with "model
        # not available"); "auto" is the only universally-valid choice, so we
        # offer just that. A plan that enables more models can extend this.
        models=(ModelChoice("auto", "Auto (Copilot picks model)"),),
        default_model="auto",
        supports_effort=True,
        effort_values=("none", "low", "medium", "high", "xhigh", "max"),
        supports_iteration_model=True,
        auth_modes=(_HOST_COPILOT, _TOKEN_COPILOT),
        version_cmd=("copilot", "--version"),
        install_hint="Install: npm install -g @github/copilot (needs a GitHub Copilot plan)",
        docs_url="https://docs.github.com/en/copilot/concepts/agents/about-copilot-cli",
    ),
    AIProvider.codex: ProviderCapabilities(
        provider=AIProvider.codex,
        cli="codex",
        models=(
            ModelChoice("", "Default (codex config)"),
            ModelChoice("gpt-5.5", "GPT-5.5"),
            ModelChoice("gpt-5-codex", "GPT-5 Codex"),
            ModelChoice("o3", "o3 (reasoning)"),
        ),
        default_model="",
        supports_effort=True,
        effort_values=("minimal", "low", "medium", "high"),
        supports_iteration_model=True,
        auth_modes=(_HOST_CODEX, _API_KEY_CODEX),
        version_cmd=("codex", "--version"),
        install_hint="Install: npm install -g @openai/codex",
        docs_url="https://developers.openai.com/codex/cli",
    ),
}


def capabilities_for(provider: AIProvider) -> ProviderCapabilities:
    """Return the capability descriptor for ``provider``."""
    return CAPABILITIES[provider]


def resolve_model(
    provider: AIProvider, model: str | None, effort: str | None
) -> tuple[str | None, str | None]:
    """Map a skill's ``model``/``effort`` onto the provider's native values.

    Claude is exact pass-through (today's behaviour). For other providers,
    a model id not in the provider's list falls back to its default, and an
    unsupported effort is dropped — both logged. Empty strings mean "use the
    CLI default" and resolve to ``None`` so the adapter omits the flag.
    """
    caps = CAPABILITIES[provider]

    if provider == AIProvider.claude:
        resolved = (model or None, effort or None)
        logger.debug(
            "ai_model_resolved",
            provider="claude",
            requested_model=model or "",
            resolved_model=resolved[0],
            resolved_effort=resolved[1],
        )
        return resolved

    valid_ids = {m.id for m in caps.models if m.id}
    if model and model in valid_ids:
        resolved_model: str | None = model
    else:
        resolved_model = caps.default_model or None
        if model:
            logger.info(
                "ai_model_fallback",
                provider=provider.value,
                requested=model,
                used=resolved_model,
            )

    if effort and caps.supports_effort and effort in caps.effort_values:
        resolved_effort: str | None = effort
    else:
        resolved_effort = None
        if effort:
            logger.info("ai_effort_dropped", provider=provider.value, requested=effort)

    logger.debug(
        "ai_model_resolved",
        provider=provider.value,
        requested_model=model or "",
        resolved_model=resolved_model,
        resolved_effort=resolved_effort,
    )
    return (resolved_model, resolved_effort)
