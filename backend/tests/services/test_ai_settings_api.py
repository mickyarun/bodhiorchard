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

import pytest
from fastapi import HTTPException

from app.api.v1.ai_settings import serialize_provider
from app.api.v1.settings_claude import _resolve_provider
from app.models.organization import AIProvider


@pytest.mark.parametrize("provider", list(AIProvider))
def testserialize_provider_shape(provider: AIProvider) -> None:
    payload = serialize_provider(provider)
    assert payload["provider"] == provider.value
    assert payload["models"], "every provider exposes at least one model"
    assert {m["value"] for m in payload["auth_modes"]}, "auth modes present"
    assert payload["install_hint"]
    assert payload["docs_url"].startswith("http")
    # auth_modes carry the secret requirement flag the wizard needs.
    assert all("requires_secret" in m for m in payload["auth_modes"])


def test_resolve_provider_defaults_and_validates() -> None:
    # None -> keep the org's current provider.
    assert _resolve_provider(None, AIProvider.codex) is AIProvider.codex
    # Valid string -> that provider.
    assert _resolve_provider("copilot", AIProvider.claude) is AIProvider.copilot
    # Invalid string -> 400.
    with pytest.raises(HTTPException) as exc:
        _resolve_provider("gemini", AIProvider.claude)
    assert exc.value.status_code == 400
