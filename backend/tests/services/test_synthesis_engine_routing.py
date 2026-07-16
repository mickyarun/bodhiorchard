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

"""How the synthesis engine adapts to the org's provider.

Synthesis is driven by write_synthesis_feature over the cluster payload the
prompt already carries — it does not read the repository. So a provider without
file access (Ollama) must still be able to run it, from the payload alone. These
tests pin how the engine routes to each kind of provider.
"""

import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.organization import AIProvider, Organization
from app.services.claude_runner import NO_REPO_CONTEXT, ClaudeRunResult
from app.services.scan.synthesis.runner import (
    _SYNTHESIS_TOOLS,
    AgentCliEngine,
    SynthesisRequest,
)

REPO_DIR = "/tmp/clone/terraform-examples"


def _org(provider: AIProvider) -> Organization:
    return Organization(id=uuid.uuid4(), name="T", slug="t", ai_provider=provider)


def _request(org: Organization | None) -> SynthesisRequest:
    return SynthesisRequest(
        prompt="synthesise features",
        working_dir=REPO_DIR,
        repo_name="terraform-examples",
        mcp_backend_url="http://backend",
        mcp_token="tok",
        org=org,
    )


async def _run_and_capture(org: Organization | None) -> dict[str, Any]:
    """Run the engine with run_agent mocked; return what it was called with."""
    run_agent = AsyncMock(return_value=ClaudeRunResult(success=True, output="done"))
    with patch("app.services.scan.synthesis.runner.run_agent", run_agent):
        await AgentCliEngine().run(_request(org))
    _org_arg, _prompt, working_dir, config, _cb = run_agent.await_args.args
    return {"working_dir": working_dir, "config": config}


async def test_ollama_runs_synthesis_without_the_repo_path() -> None:
    """The bug this fixes: Ollama can't read files, but synthesis doesn't need
    to — it works off the cluster payload. So it must NOT be handed a repo path
    (which the capability gate would refuse), and must be handed the one tool it
    drives, since the in-process loop has no "empty means all"."""
    captured = await _run_and_capture(_org(AIProvider.ollama))
    assert captured["working_dir"] == NO_REPO_CONTEXT
    assert captured["config"].mcp is not None
    assert captured["config"].mcp.tool_names == list(_SYNTHESIS_TOOLS)
    # The in-process loop resolves the org from here, not from a token.
    assert captured["config"].mcp.org_id is not None


@pytest.mark.parametrize("provider", [AIProvider.claude, AIProvider.copilot, AIProvider.codex])
async def test_cli_providers_keep_the_repo_path_and_full_tool_set(
    provider: AIProvider,
) -> None:
    """Regression guard: a file-capable provider is unchanged — it still gets
    the working_dir so it can Read files to split ambiguous clusters, and the
    empty tool list that means "expose everything" on the CLI path."""
    captured = await _run_and_capture(_org(provider))
    assert captured["working_dir"] == REPO_DIR
    assert captured["config"].mcp is not None
    assert captured["config"].mcp.tool_names == []


async def test_no_org_falls_back_to_claude_behaviour() -> None:
    """A None org (engine-mocked unit paths) routes as Claude: repo path kept."""
    captured = await _run_and_capture(None)
    assert captured["working_dir"] == REPO_DIR
