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

The descriptor types live in ``capability_types`` and are re-exported here, so
callers have a single import site. ``resolve_model`` lives in
``model_resolution`` (it reads this table, so importing it back would cycle).

Model ids / effort levels are best-effort and verified against the installed
CLIs where possible; ``resolve_model`` degrades unknown values to the provider
default, so a stale id is safe (logged), never fatal.
"""

from app.models.organization import AIProvider
from app.services.ai_runner.capability_types import (
    AuthModeSpec,
    ModelChoice,
    ProviderCapabilities,
)
from app.services.ai_runner.ollama_models import (
    OLLAMA_DEFAULT_BASE_URL,
    OLLAMA_HOST_ENV,
    ollama_probe,
)

__all__ = [
    "CAPABILITIES",
    "AuthModeSpec",
    "ModelChoice",
    "ProviderCapabilities",
    "capabilities_for",
]

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
# Ollama has no credential at all — "host" here means "no auth", not "inherit a
# login". The env var names the base URL so the auth dispatcher preserves it.
_HOST_OLLAMA = AuthModeSpec("host", "Local Ollama (no auth)", False, (OLLAMA_HOST_ENV,))


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
    AIProvider.ollama: ProviderCapabilities(
        provider=AIProvider.ollama,
        # No CLI: this provider speaks HTTP to a local server, so there is no
        # binary to version-check. ``preflight`` is the liveness signal.
        cli=None,
        version_cmd=None,
        # Populated at runtime from the org's own host — see dynamic_models.
        models=(),
        default_model="",
        # Ollama's reasoning switch is a boolean, not a level, so it rides
        # supports_thinking rather than effort.
        supports_effort=False,
        effort_values=(),
        supports_iteration_model=True,
        supports_thinking=True,
        # Tools work in-process; files and session resume have no analogue in a
        # stateless HTTP call, so run_agent blocks the features needing them
        # rather than letting them return plausible emptiness.
        supports_mcp=True,
        supports_files=False,
        supports_resume=False,
        dynamic_models=True,
        requires_base_url=True,
        default_base_url=OLLAMA_DEFAULT_BASE_URL,
        # Local inference on CPU is roughly an order of magnitude slower than a
        # hosted API; callers' timeouts assume the latter.
        timeout_multiplier=4.0,
        max_turns_cap=8,
        auth_modes=(_HOST_OLLAMA,),
        install_hint=(
            "Install Ollama (https://ollama.com), then `ollama pull qwen3`. "
            "Only models with the `tools` capability can run agents."
        ),
        docs_url="https://docs.ollama.com",
        preflight=ollama_probe,
    ),
}


def capabilities_for(provider: AIProvider) -> ProviderCapabilities:
    """Return the capability descriptor for ``provider``."""
    return CAPABILITIES[provider]
