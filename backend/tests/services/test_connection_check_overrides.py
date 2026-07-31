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

""" "Test connection" must test what the user is looking at.

A hosted Ollama entered in the Settings form populates the model dropdown —
because that probe reads the typed address — but "Test connection" read the
saved address instead, so a host typed and not yet saved was tested against
localhost and reported broken. These pin that the connection test honours the
on-screen overrides, and still falls back to the stored value without them.
"""

import uuid
from types import SimpleNamespace
from typing import Any

from app.models.organization import AIProvider
from app.services.ai_runner import connection_check
from app.services.ai_runner.ollama_models import OLLAMA_HOST_ENV


def _ollama_org(base_url: str | None) -> Any:
    """An Ollama org with no stored credential (no-auth / host mode)."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        ai_provider=AIProvider.ollama,
        ai_base_url=base_url,
        ai_model="qwen3",
        ai_thinking=False,
        claude_api_key_encrypted=None,
        claude_auth_mode="host",
    )


def _capture_env(monkeypatch: Any) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def _fake_check(provider: Any, env_extra: Any, timeout: Any) -> dict[str, Any]:
        seen["provider"] = provider
        seen["env"] = env_extra or {}
        return {"test_passed": True}

    monkeypatch.setattr(connection_check, "check_connection", _fake_check)
    return seen


async def test_a_typed_address_is_tested_not_the_empty_saved_one(monkeypatch: Any) -> None:
    """The field's exact failure: nothing saved yet, so the old path probed
    localhost while the dropdown had already listed the typed host's models."""
    seen = _capture_env(monkeypatch)

    await connection_check.check_provider_connection(
        _ollama_org(base_url=None),
        base_url="https://gw.example.com/ollama",
        model="qwen3",
        thinking=False,
    )

    assert seen["env"][OLLAMA_HOST_ENV] == "https://gw.example.com/ollama"


async def test_no_overrides_still_tests_the_saved_address(monkeypatch: Any) -> None:
    """An empty body must reproduce the original behaviour — other callers, and
    the auto-test right after a save, rely on it."""
    seen = _capture_env(monkeypatch)

    await connection_check.check_provider_connection(
        _ollama_org("https://saved.example.com/ollama")
    )

    assert seen["env"][OLLAMA_HOST_ENV] == "https://saved.example.com/ollama"


async def test_a_partial_override_falls_back_to_the_saved_address(monkeypatch: Any) -> None:
    """Overriding only the model must not blank the host — each field falls back
    independently, so a thinking-toggle test still hits the saved server."""
    seen = _capture_env(monkeypatch)

    await connection_check.check_provider_connection(
        _ollama_org("https://saved.example.com/ollama"), thinking=True
    )

    assert seen["env"][OLLAMA_HOST_ENV] == "https://saved.example.com/ollama"
