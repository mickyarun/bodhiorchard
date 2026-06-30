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

"""Provider-aware connection test for the setup wizard / settings UI.

Generalizes the old Claude-only ``test_claude_connection``: run the selected
provider's version command, then a trivial prompt through that provider's
adapter. Returns the same dict shape the existing UI consumes, plus a
``provider`` field and a provider-specific install hint on a missing CLI.
"""

import asyncio
import shutil
from typing import Any

from app.models.organization import AIProvider, Organization
from app.services.ai_runner.capabilities import capabilities_for
from app.services.ai_runner.registry import provider_for
from app.services.ai_runner.subprocess_env import build_provider_env
from app.services.claude_runner import NO_REPO_CONTEXT, ClaudeRunnerConfig

_PING_PROMPT = "Reply with exactly: BODHIORCHARD_CONNECTION_OK"


async def _cli_version(provider: AIProvider, env: dict[str, str]) -> str | None:
    """Run the provider's version command; return its output or None.

    Uses ``create_subprocess_exec`` (argument vector, no shell) so there is no
    shell-injection surface — the same safe pattern ``claude_runner`` uses.
    """
    cmd = capabilities_for(provider).version_cmd
    binary = shutil.which(cmd[0])
    if binary is None:
        return None
    try:
        proc = await asyncio.create_subprocess_exec(
            binary,
            *cmd[1:],
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=15)
        if proc.returncode == 0:
            return stdout.decode("utf-8", errors="replace").strip()[:100]
    except (TimeoutError, OSError):
        pass
    return None


async def check_provider_connection(org: Organization) -> dict[str, Any]:
    """Verify the org's provider CLI is installed and authenticated.

    Callers must apply the org's auth to the process env first (the same
    contract the Claude-only test had). Returns ``cli_available``,
    ``cli_version``, ``test_passed``, ``output``, ``error``, ``provider``.
    """
    provider = org.ai_provider or AIProvider.claude
    caps = capabilities_for(provider)
    # ``env`` is only for the version probe below; the provider's ``.run()``
    # rebuilds its own env from ``os.environ`` (which the caller already
    # populated via ``apply_claude_auth_to_env``).
    env = build_provider_env(provider, None)

    version = await _cli_version(provider, env)
    result: dict[str, Any] = {
        "provider": provider.value,
        "cli_available": version is not None,
        "cli_version": version,
        "test_passed": False,
        "output": "",
        "error": None,
    }
    if version is None:
        result["error"] = caps.install_hint
        return result

    run = await provider_for(org).run(
        _PING_PROMPT,
        NO_REPO_CONTEXT,
        ClaudeRunnerConfig(max_turns=1, timeout_seconds=90),
    )
    result["test_passed"] = run.success
    result["output"] = (run.output or "")[:200]
    result["error"] = run.error
    return result
