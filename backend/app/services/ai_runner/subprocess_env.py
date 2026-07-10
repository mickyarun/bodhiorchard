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
import sys
from collections.abc import Mapping

from app.models.organization import AIProvider

# Generic POSIX plumbing every CLI needs (locate the binary, read its config
# dir under HOME, keep git/node happy). Mirrors the Claude whitelist base.
_POSIX_BASE: frozenset[str] = frozenset(
    {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TERM", "TMPDIR", "SHELL"}
)

# Windows-essential plumbing — the win32 counterparts to the POSIX vars above.
# Non-secret and absent on macOS / Linux, so listing them unconditionally is a
# no-op off-Windows. Without ``SYSTEMROOT`` an npm ``.CMD`` CLI shim (which
# bootstraps ``cmd.exe`` + node) exits immediately with no output; the rest are
# needed once the CLI spawns node/git and writes scratch files. Kept in sync
# with ``claude_guard.env_filter._WINDOWS_ENV``.
_WINDOWS_ENV: frozenset[str] = frozenset(
    {
        "SYSTEMROOT",
        "SYSTEMDRIVE",
        "WINDIR",
        "COMSPEC",
        "PATHEXT",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "APPDATA",
        "LOCALAPPDATA",
        "NUMBER_OF_PROCESSORS",
        "PROCESSOR_ARCHITECTURE",
    }
)

_BASE_WHITELIST: frozenset[str] = _POSIX_BASE | _WINDOWS_ENV

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
    # On Windows, match case-insensitively — env keys carry arbitrary case
    # (``SYSTEMROOT`` vs ``SystemRoot``) and are semantically case-insensitive,
    # so an exact test would drop the essential win32 vars. On POSIX, names are
    # case-sensitive and the whitelist is canonical, so we keep the exact match
    # and leave macOS/Linux behaviour byte-for-byte unchanged.
    if sys.platform == "win32":
        allowed_lower = {name.lower() for name in allowed}
        base: dict[str, str] = {k: v for k, v in os.environ.items() if k.lower() in allowed_lower}
    else:
        base = {k: v for k, v in os.environ.items() if k in allowed}
    if env_extra:
        for key, value in env_extra.items():
            if value == "":
                base.pop(key, None)
            else:
                base[key] = value
    return base
