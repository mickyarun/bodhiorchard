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
from app.services.ai_runner.capability_gate import adapt_config
from app.services.ai_runner.registry import provider_instance
from app.services.ai_runner.subprocess_env import build_provider_env
from app.services.claude_runner import NO_REPO_CONTEXT, ClaudeRunnerConfig

_PING_PROMPT = "Reply with exactly: BODHIORCHARD_CONNECTION_OK"


async def _cli_version(provider: AIProvider, env: dict[str, str]) -> str | None:
    """Run the provider's version command; return its output or None.

    Uses ``create_subprocess_exec`` (argument vector, no shell) so there is no
    shell-injection surface — the same safe pattern ``claude_runner`` uses.

    Returns None for a provider with no ``version_cmd``; such providers are
    HTTP-based and are checked with ``preflight`` instead.
    """
    cmd = capabilities_for(provider).version_cmd
    if cmd is None:
        return None
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


async def check_connection(
    provider: AIProvider, env_extra: dict[str, str] | None = None
) -> dict[str, Any]:
    """Verify ``provider`` is installed/reachable and can authenticate.

    Org-independent core. ``env_extra`` carries provisional credentials for
    the pre-init setup wizard (where no org/process-env exists yet); for the
    authenticated settings path it's ``None`` and the caller has already put
    the org's auth into ``os.environ``. Returns ``cli_available``,
    ``cli_version``, ``test_passed``, ``output``, ``error``, ``provider``.

    A provider is "available" if its CLI version command works, or — for
    HTTP-based providers with no CLI — if its ``preflight`` probe answers.
    Which applies is decided by the capability table, not by naming a
    provider here.
    """
    caps = capabilities_for(provider)
    env = build_provider_env(provider, env_extra)

    if caps.preflight is not None:
        version = await caps.preflight(env_extra)
    else:
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

    run = await provider_instance(provider).run(
        _PING_PROMPT,
        NO_REPO_CONTEXT,
        ClaudeRunnerConfig(max_turns=1, timeout_seconds=90, env_extra=env_extra),
    )
    result["test_passed"] = run.success
    result["output"] = (run.output or "")[:200]
    result["error"] = run.error
    return result


async def check_provider_connection(org: Organization) -> dict[str, Any]:
    """Verify the org's provider is reachable and can authenticate.

    The org's own host/model/thinking settings are resolved through the same
    seam a real run uses, so "Test connection" checks the configuration the org
    will actually run with. Without that, a provider pointed at a remote host
    would silently be probed on localhost — reporting a confident green for a
    host nobody tested, or an install hint for a config that was fine.
    """
    provider = org.ai_provider or AIProvider.claude
    probe = adapt_config(capabilities_for(provider), org, ClaudeRunnerConfig())
    return await check_connection(provider, probe.env_extra)
