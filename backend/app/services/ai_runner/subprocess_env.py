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

"""Whitelisted subprocess env for the non-Claude provider CLIs.

Mirrors ``claude_guard.env_filter.build_claude_env`` (narrow the child's view
so a prompt-injection escape has nothing valuable to exfiltrate) but passes
each provider's own auth vars instead of Anthropic's — Copilot needs the
GitHub tokens that the Claude whitelist deliberately strips.
"""

import os
from collections.abc import Mapping

from app.models.organization import AIProvider

# Generic POSIX plumbing every CLI needs (locate the binary, read its config
# dir under HOME, keep git/node happy). Mirrors the Claude whitelist base.
_BASE_WHITELIST: frozenset[str] = frozenset(
    {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "TMPDIR", "SHELL"}
)

# Provider-specific vars to pass through: auth credentials + CLI config dirs.
# Kept explicit (not derived) so it's obvious exactly what each child can see.
_PROVIDER_PASSTHROUGH: dict[AIProvider, frozenset[str]] = {
    AIProvider.claude: frozenset(
        {"ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN"}
    ),
    AIProvider.copilot: frozenset({"GH_TOKEN", "COPILOT_GITHUB_TOKEN", "GITHUB_TOKEN"}),
    AIProvider.codex: frozenset({"OPENAI_API_KEY", "CODEX_HOME", "OPENAI_BASE_URL"}),
}


def build_provider_env(
    provider: AIProvider, env_extra: Mapping[str, str] | None
) -> dict[str, str]:
    """Return the env mapping for ``provider``'s subprocess.

    Only the base POSIX vars plus the provider's own passthrough vars are
    inherited. ``env_extra`` is merged on top with the same convention as
    ``build_claude_env``: a value of ``""`` removes the var entirely.
    """
    allowed = _BASE_WHITELIST | _PROVIDER_PASSTHROUGH.get(provider, frozenset())
    base: dict[str, str] = {k: v for k, v in os.environ.items() if k in allowed}
    if env_extra:
        for key, value in env_extra.items():
            if value == "":
                base.pop(key, None)
            else:
                base[key] = value
    return base
