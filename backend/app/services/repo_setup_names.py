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

"""Names the repo-setup pipeline writes into a tracked repository.

One place for the folder, MCP server key and env var names that land in a
developer's checkout, so the Claude path (``repo_setup``) and the
Codex/Copilot path (``scan.agent_repo_config``) can't drift apart.

Repos set up before the Glideship rename carry the legacy names: a
``.bodhiorchard/`` folder, a ``bodhiorchard`` MCP server key and a
``BODHIORCHARD_MCP_TOKEN`` export. Those keep working because the bridge and
the hook scripts read the new env var first and fall back to the legacy one,
and nothing here deletes a legacy folder. A re-run of setup switches the
config over to the new names in the setup PR.

The server-managed git worktrees (``.bodhiorchard/<branch>``, ``scan-wt``,
``setup-work``) are a separate, gitignored concern and stay where they are.
"""

from __future__ import annotations

from app.mcp.bridge_env import BACKEND_URL_ENV

REPO_DIR = ".glideship"

MCP_SERVER_KEY = "glideship"
LEGACY_MCP_SERVER_KEY = "bodhiorchard"

BRIDGE_PATH = f"{REPO_DIR}/mcp_bridge.py"
HOOKS_DIR = f"{REPO_DIR}/hooks"


def mcp_server_entry(backend_url: str) -> dict[str, object]:
    """The stdio server entry for ``.mcp.json``-shaped configs (token-free).

    The developer exports the token themselves; only the backend URL is
    baked in.
    """
    return {
        "command": "python3",
        "args": [BRIDGE_PATH],
        "env": {BACKEND_URL_ENV: backend_url},
    }
