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

"""Design-system extraction must not require a filesystem.

The payload is the design files this module already read and inlines into the
prompt — the agent is handed the source rather than sent to find it. Gating the
whole extraction on file access forced orgs on an HTTP provider onto the regex
fallback (web/Vuetify idioms only) despite their provider being able to do the
real work. These tests pin the routing for both provider shapes.
"""

import uuid
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from app.models.organization import AIProvider, Organization
from app.services.claude_runner import NO_REPO_CONTEXT, ClaudeRunResult
from app.services.design_system_extractor import _cli_available, _llm_extract
from app.services.platforms import Platform, detect_platform

REPO = Path("/tmp/clone/webapp")
_MOD = "app.services.design_system_extractor"


def _org(provider: AIProvider) -> Organization:
    return Organization(id=uuid.uuid4(), name="T", slug="t", ai_provider=provider)


def test_http_provider_without_a_cli_is_available() -> None:
    """No binary to probe, and no filesystem needed — it can still extract."""
    assert _cli_available(_org(AIProvider.ollama)) is True


@pytest.mark.parametrize("provider", [AIProvider.copilot, AIProvider.codex])
def test_cli_providers_still_probe_their_binary(provider: AIProvider) -> None:
    """Regression guard: a CLI provider with no binary installed can't run."""
    with patch(f"{_MOD}.shutil.which", return_value=None):
        assert _cli_available(_org(provider)) is False
    with patch(f"{_MOD}.shutil.which", return_value="/usr/bin/x"):
        assert _cli_available(_org(provider)) is True


def _platform() -> Platform:
    """Any real platform — the routing under test is provider-driven, not
    platform-driven, so the fallback the registry returns here is enough."""
    return detect_platform(Path(__file__).parent)


async def _extract(provider: AIProvider, contents: dict[str, str]) -> dict[str, Any]:
    run_agent = AsyncMock(
        return_value=ClaudeRunResult(success=True, output="# Design System\n\nTokens.")
    )
    with patch(f"{_MOD}.run_agent", run_agent):
        await _llm_extract(REPO, contents, _platform(), _org(provider))
    _org_arg, prompt, working_dir, _config = run_agent.await_args.args
    return {"prompt": prompt, "working_dir": working_dir}


@pytest.mark.asyncio
async def test_file_less_provider_gets_no_repo_path_and_no_read_instructions() -> None:
    """The bug: it was handed repo_path (which run_agent refuses outright) and
    told to read from disk — an instruction it cannot follow reads as a broken
    environment, so it gives up instead of using the inlined source."""
    big = "x" * 20_000
    captured = await _extract(AIProvider.ollama, {"theme.css": ":root{}", "big.css": big})

    assert captured["working_dir"] == NO_REPO_CONTEXT
    assert "no filesystem access" in captured["prompt"]
    assert "read from disk" not in captured["prompt"]
    # The inlined source is still there — that's the actual payload.
    assert "theme.css" in captured["prompt"]


@pytest.mark.asyncio
async def test_file_capable_provider_keeps_the_repo_path_and_read_hints() -> None:
    """Regression guard: Claude's behaviour is unchanged."""
    big = "x" * 20_000
    captured = await _extract(AIProvider.claude, {"theme.css": ":root{}", "big.css": big})

    assert captured["working_dir"] == REPO
    assert "read from disk" in captured["prompt"]
    assert "code_query" in captured["prompt"]
