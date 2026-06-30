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
from app.services.ai_runner.capabilities import (
    CAPABILITIES,
    capabilities_for,
    resolve_model,
)


def test_every_provider_has_capabilities() -> None:
    """Each enum member has a descriptor with at least one auth mode + model."""
    for provider in AIProvider:
        caps = capabilities_for(provider)
        assert caps.auth_modes, provider
        assert caps.models, provider
        assert caps.version_cmd[0] == caps.cli


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


def test_capabilities_table_covers_all_enum_members() -> None:
    """No provider enum member is missing from the table."""
    assert set(CAPABILITIES) == set(AIProvider)
