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

"""Provider-aware ``apply_claude_auth_to_env`` (Copilot / Codex) tests.

Verifies each provider's credential maps to the right env var and that
applying one provider clears the others' app-managed vars, while host-owned
credentials (a compose ``ANTHROPIC_API_KEY``, the host's ``GH_TOKEN``) are
preserved.
"""

import os
from collections.abc import Iterator

import pytest

from app.core.encryption import encrypt_secret
from app.models.organization import AIProvider, Organization
from app.services.claude_env import apply_claude_auth_to_env

_VARS = ("ANTHROPIC_API_KEY", "CLAUDE_CODE_OAUTH_TOKEN", "COPILOT_GITHUB_TOKEN", "OPENAI_API_KEY")


@pytest.fixture(autouse=True)
def _isolate_env() -> Iterator[None]:
    saved = {k: os.environ.get(k) for k in (*_VARS, "GH_TOKEN")}
    for key in (*_VARS, "GH_TOKEN"):
        os.environ.pop(key, None)
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _org(provider: AIProvider, mode: str, secret: str | None) -> Organization:
    return Organization(
        ai_provider=provider,
        claude_auth_mode=mode,
        claude_api_key_encrypted=encrypt_secret(secret) if secret else None,
    )


def test_copilot_api_key_sets_copilot_token_only() -> None:
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-leftover"
    apply_claude_auth_to_env(_org(AIProvider.copilot, "api_key", "ghp_token"))
    assert os.environ["COPILOT_GITHUB_TOKEN"] == "ghp_token"
    # Other providers' app-managed vars are cleared so they can't shadow it.
    assert "ANTHROPIC_API_KEY" not in os.environ
    assert "OPENAI_API_KEY" not in os.environ


def test_copilot_host_preserves_gh_token() -> None:
    os.environ["GH_TOKEN"] = "gho_host_login"
    apply_claude_auth_to_env(_org(AIProvider.copilot, "host", None))
    # GH_TOKEN is the host's git credential — never app-managed, never cleared.
    assert os.environ["GH_TOKEN"] == "gho_host_login"
    assert "COPILOT_GITHUB_TOKEN" not in os.environ


def test_codex_api_key_sets_openai_key() -> None:
    apply_claude_auth_to_env(_org(AIProvider.codex, "api_key", "sk-openai-xyz"))
    assert os.environ["OPENAI_API_KEY"] == "sk-openai-xyz"
    assert "COPILOT_GITHUB_TOKEN" not in os.environ


def test_claude_api_key_unchanged_behaviour() -> None:
    os.environ["COPILOT_GITHUB_TOKEN"] = "stale"
    apply_claude_auth_to_env(_org(AIProvider.claude, "api_key", "sk-ant-123"))
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-123"
    # A stale copilot token from a previous provider is cleared.
    assert "COPILOT_GITHUB_TOKEN" not in os.environ


def test_claude_host_preserves_compose_key() -> None:
    os.environ["ANTHROPIC_API_KEY"] = "sk-ant-compose"
    apply_claude_auth_to_env(_org(AIProvider.claude, "host", None))
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-compose"
