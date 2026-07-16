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

"""Unit tests for the AI-settings capabilities serializer + provider resolver."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.api.v1.ai_settings import serialize_provider, with_dynamic_models
from app.api.v1.settings_claude import _resolve_provider
from app.models.organization import AIProvider
from app.services.ai_runner.capabilities import capabilities_for


@pytest.mark.parametrize("provider", list(AIProvider))
def testserialize_provider_shape(provider: AIProvider) -> None:
    payload = serialize_provider(provider)
    assert payload["provider"] == provider.value
    # A dynamic provider reads its models off the org's own host, so it ships
    # none here and they are filled in later from the live server.
    assert payload["models"] or payload["dynamic_models"], "models, or a way to find them"
    assert {m["value"] for m in payload["auth_modes"]}, "auth modes present"
    assert payload["install_hint"]
    assert payload["docs_url"].startswith("http")
    # auth_modes carry the secret requirement flag the wizard needs.
    assert all("requires_secret" in m for m in payload["auth_modes"])
    # The UI gates its controls on these, so every provider must answer them.
    for flag in ("supports_thinking", "supports_mcp", "supports_files", "requires_base_url"):
        assert isinstance(payload[flag], bool), flag
    # A provider needing a base URL must say what it defaults to, or the
    # wizard has nothing to prefill and no way to probe before setup.
    if payload["requires_base_url"]:
        assert payload["default_base_url"], provider


def test_resolve_provider_defaults_and_validates() -> None:
    # None -> keep the org's current provider.
    assert _resolve_provider(None, AIProvider.codex) is AIProvider.codex
    # Valid string -> that provider.
    assert _resolve_provider("copilot", AIProvider.claude) is AIProvider.copilot
    # Invalid string -> 400.
    with pytest.raises(HTTPException) as exc:
        _resolve_provider("gemini", AIProvider.claude)
    assert exc.value.status_code == 400


async def test_dynamic_models_are_filled_from_the_live_host() -> None:
    """The host's tool-capable models are what the UI must offer.

    Without this the dropdown is empty for Ollama and the capability filter
    never runs at all — a user could pick a model that fails at the first
    tool call, or have nothing to pick.
    """
    payloads = [serialize_provider(p) for p in AIProvider]
    with patch(
        "app.api.v1.ai_settings.list_tool_models",
        AsyncMock(return_value=["qwen3:latest", "llama3.2:latest"]),
    ):
        filled = await with_dynamic_models(payloads, "http://gpu-box:11434")
    by_name = {p["provider"]: p for p in filled}
    assert [m["id"] for m in by_name["ollama"]["models"]] == ["qwen3:latest", "llama3.2:latest"]
    # A static provider's list must not be touched by the probe.
    assert by_name["claude"]["models"] == serialize_provider(AIProvider.claude)["models"]


async def test_the_probe_uses_the_orgs_host_not_a_default() -> None:
    """An org pointed at a remote box must not be probed on localhost."""
    probe = AsyncMock(return_value=[])
    with patch("app.api.v1.ai_settings.list_tool_models", probe):
        await with_dynamic_models([serialize_provider(AIProvider.ollama)], "http://gpu-box:11434")
    assert probe.await_args.args[0] == "http://gpu-box:11434"


async def test_no_org_host_falls_back_to_the_providers_default() -> None:
    """The setup wizard has no org yet, so it probes the default address."""
    probe = AsyncMock(return_value=[])
    with patch("app.api.v1.ai_settings.list_tool_models", probe):
        await with_dynamic_models([serialize_provider(AIProvider.ollama)], None)
    assert probe.await_args.args[0] == capabilities_for(AIProvider.ollama).default_base_url


async def test_an_unreachable_host_leaves_the_page_usable() -> None:
    """Settings must render when Ollama is down — every other provider's
    configuration lives on the same page."""
    with patch("app.api.v1.ai_settings.list_tool_models", AsyncMock(return_value=[])):
        filled = await with_dynamic_models([serialize_provider(p) for p in AIProvider], None)
    assert {p["provider"] for p in filled} == {p.value for p in AIProvider}
    assert next(p for p in filled if p["provider"] == "ollama")["models"] == []
