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

"""Switching an org back to host mode stops using the key the app injected.

Host mode keeps a credential the host or compose file supplied, but a key the
app itself put into the process env for an earlier ``api_key`` choice has to
go, or every later agent run keeps billing that key until a restart.
"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest

from app.core.encryption import encrypt_secret
from app.models.organization import AIProvider, Organization
from app.services import claude_env
from app.services.claude_env import apply_claude_auth_to_env

_VAR = "ANTHROPIC_API_KEY"


@pytest.fixture(autouse=True)
def _isolate_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    # Forget what earlier tests' env changes left in the module's bookkeeping.
    monkeypatch.setattr(claude_env, "_app_left", {})
    monkeypatch.setattr(claude_env, "_host_value", {})
    saved = {k: os.environ.get(k) for k in (_VAR, "CLAUDE_CODE_OAUTH_TOKEN", "OPENAI_API_KEY")}
    for key in saved:
        os.environ.pop(key, None)
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _org(
    mode: str, secret: str | None = None, provider: AIProvider = AIProvider.claude
) -> Organization:
    return Organization(
        ai_provider=provider,
        claude_auth_mode=mode,
        claude_api_key_encrypted=encrypt_secret(secret) if secret else None,
    )


def test_host_after_api_key_drops_the_injected_key() -> None:
    apply_claude_auth_to_env(_org("api_key", "sk-ant-org-key"))
    apply_claude_auth_to_env(_org("host"))
    assert _VAR not in os.environ


def test_host_after_api_key_brings_back_the_compose_key() -> None:
    os.environ[_VAR] = "sk-ant-compose"
    apply_claude_auth_to_env(_org("api_key", "sk-ant-org-key"))
    assert os.environ[_VAR] == "sk-ant-org-key"
    apply_claude_auth_to_env(_org("host"))
    assert os.environ[_VAR] == "sk-ant-compose"


def test_changing_the_key_twice_still_restores_the_original() -> None:
    os.environ[_VAR] = "sk-ant-compose"
    apply_claude_auth_to_env(_org("api_key", "sk-ant-first"))
    apply_claude_auth_to_env(_org("api_key", "sk-ant-second"))
    apply_claude_auth_to_env(_org("host"))
    assert os.environ[_VAR] == "sk-ant-compose"


def test_host_leaves_a_key_someone_else_set_after_the_injection() -> None:
    apply_claude_auth_to_env(_org("api_key", "sk-ant-org-key"))
    os.environ[_VAR] = "sk-ant-operator"
    apply_claude_auth_to_env(_org("host"))
    assert os.environ[_VAR] == "sk-ant-operator"


def test_host_with_only_a_compose_key_keeps_it() -> None:
    os.environ[_VAR] = "sk-ant-compose"
    apply_claude_auth_to_env(_org("host"))
    assert os.environ[_VAR] == "sk-ant-compose"


def test_host_after_subscription_brings_back_the_compose_key() -> None:
    os.environ[_VAR] = "sk-ant-compose"
    apply_claude_auth_to_env(_org("subscription", "oat-token"))
    assert _VAR not in os.environ
    apply_claude_auth_to_env(_org("host"))
    assert os.environ[_VAR] == "sk-ant-compose"
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in os.environ


def test_host_after_api_key_then_subscription_brings_back_the_compose_key() -> None:
    os.environ[_VAR] = "sk-ant-compose"
    apply_claude_auth_to_env(_org("api_key", "sk-ant-org-key"))
    apply_claude_auth_to_env(_org("subscription", "oat-token"))
    apply_claude_auth_to_env(_org("host"))
    assert os.environ[_VAR] == "sk-ant-compose"


def test_claude_host_after_codex_brings_back_the_compose_key() -> None:
    os.environ[_VAR] = "sk-ant-compose"
    apply_claude_auth_to_env(_org("api_key", "sk-openai", provider=AIProvider.codex))
    assert _VAR not in os.environ
    apply_claude_auth_to_env(_org("host"))
    assert os.environ[_VAR] == "sk-ant-compose"
    assert "OPENAI_API_KEY" not in os.environ
