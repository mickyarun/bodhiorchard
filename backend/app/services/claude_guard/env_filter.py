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

"""Environment-variable whitelist for the ``claude`` subprocess.

Before this module existed, ``claude_runner`` spawned the CLI with
``env=None`` (full ``os.environ`` inheritance) or ``{**os.environ, **extra}``
— in either case the child saw every secret the backend holds:
``ENCRYPTION_KEY`` (Fernet key for at-rest encryption), ``DATABASE_URL``,
``SECRET_KEY`` (JWT signing key), ``GITHUB_TOKEN``, ``AWS_*``, every
``BODHIORCHARD_*`` setting.

A successful prompt-injection that escapes the Bash deny list (Layer 3) can
``echo $DATABASE_URL`` or ``echo $ENCRYPTION_KEY`` and there is nothing to
stop the value from being exfiltrated. This module narrows the child view
to the bare minimum it actually needs to run, so even if every other layer
fails there is nothing valuable to leak.
"""

from __future__ import annotations

import os
from collections.abc import Mapping

# Variables the ``claude`` child process actually needs to run.
#
# * ``PATH`` — locate the ``claude`` binary plus ``git``, ``node``, etc.
# * ``HOME`` — Claude reads ``~/.claude/`` for state in Hybrid mode. We pass
#   the real ``HOME`` rather than a sandbox dir so the host's
#   ``claude login`` session is still usable. (In Full Docker mode there is
#   no host session, so this is effectively a no-op.)
# * ``USER`` / ``LANG`` / ``LC_ALL`` / ``TERM`` / ``TMPDIR`` — generic POSIX
#   plumbing. Without these, ``git`` and ``node`` misbehave on macOS.
# * ``ANTHROPIC_API_KEY`` — the child authenticates to Anthropic with this.
#   The key itself is sensitive, but the child legitimately needs it; the
#   protection here is that *nothing else* leaks alongside it.
# * ``CLAUDE_CODE_*`` / ``DISABLE_AUTOUPDATER`` — knobs the CLI itself reads.
#
# Note: ``BODHIORCHARD_MCP_TOKEN`` and friends are intentionally absent.
# The MCP bridge receives its token via the per-call MCP JSON config's
# ``env`` block (see ``claude_runner._build_mcp_config_file``), not via
# parent-process env inheritance, so dropping them here is safe.
_CLAUDE_ENV_WHITELIST: frozenset[str] = frozenset(
    {
        "PATH",
        "HOME",
        "USER",
        "LANG",
        "LC_ALL",
        "TERM",
        "TMPDIR",
        "SHELL",
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
        "DISABLE_AUTOUPDATER",
        "DISABLE_TELEMETRY",
    }
)


def build_claude_env(env_extra: Mapping[str, str] | None) -> dict[str, str]:
    """Return the env mapping to hand to the ``claude`` child process.

    Only variables in ``_CLAUDE_ENV_WHITELIST`` are inherited from the
    parent process. ``env_extra`` (caller-supplied per-call additions, e.g.
    agent context) is then merged on top — callers are trusted to vet what
    they add. Hard-coded knobs that minimize the subprocess's telemetry /
    update chatter are set unless already provided.

    Returns a fresh ``dict`` (never ``None``) so callers can hand it
    directly to ``asyncio.create_subprocess_exec``. Note that passing
    ``env={}`` would strip ``PATH`` and break ``claude`` launch immediately
    — the whitelist is the minimum viable env.
    """
    base: dict[str, str] = {k: v for k, v in os.environ.items() if k in _CLAUDE_ENV_WHITELIST}
    base.setdefault("CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC", "1")
    base.setdefault("DISABLE_AUTOUPDATER", "1")
    if env_extra:
        base.update(env_extra)
    return base
