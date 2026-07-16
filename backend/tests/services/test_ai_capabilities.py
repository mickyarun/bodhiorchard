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

"""Unit tests for the provider capability table + model/effort resolution."""

from app.models.organization import AIProvider
from app.services.ai_runner.capabilities import CAPABILITIES, capabilities_for
from app.services.ai_runner.model_resolution import resolve_model


def test_every_provider_has_capabilities() -> None:
    """Each enum member has a usable descriptor.

    Guards the invariant that broke when ``ollama`` was added to the enum: a
    member without a table entry KeyErrors every ``for p in AIProvider``
    fan-out, which 500s the settings page and the first-run wizard.
    """
    for provider in AIProvider:
        caps = capabilities_for(provider)
        assert caps.auth_modes, provider
        # Providers that read their model list off the user's own host ship an
        # empty tuple here and fill it at runtime.
        assert caps.models or caps.dynamic_models, provider
        if caps.version_cmd is not None:
            assert caps.version_cmd[0] == caps.cli
        else:
            # No CLI to version-check, so reachability must be probeable.
            assert caps.cli is None, provider
            assert caps.preflight is not None, provider


def test_ollama_declares_no_files_and_needs_a_base_url() -> None:
    """Ollama's limits are declared, so run_agent can block what it can't do."""
    caps = capabilities_for(AIProvider.ollama)
    assert caps.supports_mcp is True
    # No filesystem and no session affinity over stateless HTTP.
    assert caps.supports_files is False
    assert caps.supports_resume is False
    # Reasoning is a boolean here, not a graded effort level.
    assert caps.supports_thinking is True
    assert caps.supports_effort is False
    assert caps.requires_base_url is True
    assert caps.default_base_url
    assert caps.max_turns_cap and caps.max_turns_cap > 0


def test_cli_providers_keep_file_access() -> None:
    """Adding Ollama must not narrow what the CLI providers may do."""
    for provider in (AIProvider.claude, AIProvider.copilot, AIProvider.codex):
        caps = capabilities_for(provider)
        assert caps.supports_files is True, provider
        assert caps.supports_mcp is True, provider
        assert caps.supports_resume is True, provider
        assert caps.requires_base_url is False, provider


def test_ollama_model_passes_through_untouched() -> None:
    """A dynamic provider's model id must not be validated against the table.

    Ollama's valid ids live on the user's host, so the static tuple is empty.
    Running it through the normal path would fall back to the default and
    silently drop every model the user actually has installed.
    """
    assert resolve_model(AIProvider.ollama, "qwen3:latest", None)[0] == "qwen3:latest"
    # Effort is not a concept here (thinking is a boolean), so it is dropped.
    assert resolve_model(AIProvider.ollama, "qwen3:latest", "high") == ("qwen3:latest", None)
    # No model requested -> let the caller decide.
    assert resolve_model(AIProvider.ollama, "", None) == (None, None)


def test_claude_is_exact_passthrough() -> None:
    """Claude resolution must not change today's behaviour."""
    assert resolve_model(AIProvider.claude, "sonnet", "high") == ("sonnet", "high")
    assert resolve_model(AIProvider.claude, "claude-haiku-4-5", "") == ("claude-haiku-4-5", None)
    assert resolve_model(AIProvider.claude, "", "") == (None, None)


def test_copilot_keeps_valid_falls_back_unknown() -> None:
    """A Claude tier falls back to Copilot's default; valid ids pass through."""
    # "sonnet" is not a Copilot model id -> default ("auto"); "high" is valid.
    assert resolve_model(AIProvider.copilot, "sonnet", "high") == ("auto", "high")
    # "auto" is a valid Copilot model id and passes through; "xhigh" is a valid effort.
    assert resolve_model(AIProvider.copilot, "auto", "xhigh") == ("auto", "xhigh")


def test_codex_default_is_none_and_effort_can_drop() -> None:
    """Codex's empty default omits --model; unsupported effort is dropped."""
    # default_model is "" -> None (adapter omits -m, codex uses its config).
    model, effort = resolve_model(AIProvider.codex, "sonnet", "high")
    assert model is None
    assert effort == "high"
    # "max" is not a Codex reasoning level -> dropped.
    assert resolve_model(AIProvider.codex, "gpt-5.5", "max") == ("gpt-5.5", None)


def test_codex_does_not_offer_chatgpt_account_rejected_models() -> None:
    """gpt-5-codex and o3 fail on a ChatGPT-login account with a hard 400.

    A listed id passes straight through to the CLI, so offering one of these
    would guarantee a failed run rather than degrade — the exact drift this
    table is supposed to prevent. If they are re-added, it must be behind an
    auth mode that actually accepts them.
    """
    codex_ids = {m.id for m in capabilities_for(AIProvider.codex).models}
    assert "gpt-5-codex" not in codex_ids
    assert "o3" not in codex_ids
    # An id not in the table still degrades cleanly to the default, so a run
    # never dies on one that slipped through from, say, stale skill frontmatter.
    assert resolve_model(AIProvider.codex, "o3", None) == (None, None)


def test_capabilities_table_covers_all_enum_members() -> None:
    """No provider enum member is missing from the table."""
    assert set(CAPABILITIES) == set(AIProvider)
