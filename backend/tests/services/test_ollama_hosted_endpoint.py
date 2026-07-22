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

"""Reaching an Ollama that is not on this machine.

Validation lives in ``test_ollama_base_url_validation``; this covers what the
client actually puts on the wire once a hosted address is allowed — the path
prefix and the bearer token. Both are invisible in the saved settings if they
are dropped: the symptom is a 404 or a 401 several layers away, so they are
asserted at the request itself.
"""

from typing import Any

import httpx
import pytest

from app.services.ai_runner import ollama_models
from app.services.ai_runner.capability_types import ProbeResult
from app.services.ai_runner.ollama_chat import OllamaChatError, chat
from app.services.ai_runner.ollama_models import (
    OLLAMA_HOST_ENV,
    clear_model_cache,
    list_tool_models,
    ollama_probe,
)

_SEEN: list[httpx.Request] = []


@pytest.fixture(autouse=True)
def _isolate() -> Any:
    """The model cache is module-global and would leak between tests."""
    _SEEN.clear()
    clear_model_cache()
    yield
    clear_model_cache()


def _install(monkeypatch: pytest.MonkeyPatch, handler: Any) -> None:
    """Route every AsyncClient in the module under test through ``handler``."""
    real_client = httpx.AsyncClient

    def factory(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(**kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", factory)


def _tags_handler(request: httpx.Request) -> httpx.Response:
    _SEEN.append(request)
    if request.url.path.endswith("/api/tags"):
        return httpx.Response(200, json={"models": [{"name": "qwen3:latest"}]})
    return httpx.Response(200, json={"capabilities": ["completion", "tools"]})


async def test_a_path_prefix_is_kept_on_every_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """A gateway that serves Ollama under a prefix must still be hit under it.

    Appending to the bare origin instead would 404 against the gateway root,
    which surfaces as "no models found" — indistinguishable from a server with
    nothing installed.
    """
    _install(monkeypatch, _tags_handler)

    models = await list_tool_models("https://gw.example.com/ollama")

    assert models == ["qwen3:latest"]
    assert [r.url.path for r in _SEEN] == ["/ollama/api/tags", "/ollama/api/show"]


async def test_a_token_is_sent_when_one_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    _install(monkeypatch, _tags_handler)

    await list_tool_models("https://gw.example.com", api_key="secret-token")

    assert all(r.headers["authorization"] == "Bearer secret-token" for r in _SEEN)


async def test_no_authorization_header_without_a_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """A local server has no auth; an empty bearer would be a header it has to
    reject or ignore, and either way it is not what we mean."""
    _install(monkeypatch, _tags_handler)

    await list_tool_models("http://localhost:11434")

    assert all("authorization" not in r.headers for r in _SEEN)


async def test_the_model_cache_does_not_cross_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    """Two orgs can share one hosted endpoint while being entitled to different
    models. Keyed on the address alone, the first org's answer would be served
    to the second."""

    def handler(request: httpx.Request) -> httpx.Response:
        _SEEN.append(request)
        token = request.headers.get("authorization", "")
        if request.url.path.endswith("/api/tags"):
            name = "alpha:latest" if token.endswith("a") else "beta:latest"
            return httpx.Response(200, json={"models": [{"name": name}]})
        return httpx.Response(200, json={"capabilities": ["tools"]})

    _install(monkeypatch, handler)

    first = await list_tool_models("https://gw.example.com", api_key="token-a")
    second = await list_tool_models("https://gw.example.com", api_key="token-b")

    assert first == ["alpha:latest"]
    assert second == ["beta:latest"]


async def test_chat_posts_under_the_prefix_with_the_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The run path, not just discovery — a prefix lost here fails every call."""

    def handler(request: httpx.Request) -> httpx.Response:
        _SEEN.append(request)
        return httpx.Response(200, json={"message": {"role": "assistant", "content": "ok"}})

    _install(monkeypatch, handler)

    message = await chat(
        "https://gw.example.com/ollama",
        "qwen3:latest",
        [{"role": "user", "content": "hi"}],
        timeout_s=5,
        api_key="tok",
    )

    assert message["content"] == "ok"
    assert _SEEN[0].url.path == "/ollama/api/chat"
    assert _SEEN[0].headers["authorization"] == "Bearer tok"


async def test_a_rejected_credential_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """401 and "model missing" both surface as a failed run otherwise, and the
    operator has no way to tell which setting to go fix."""
    _install(monkeypatch, lambda request: httpx.Response(401, json={"error": "unauthorized"}))

    with pytest.raises(OllamaChatError, match="rejected the credential"):
        await chat(
            "https://gw.example.com",
            "qwen3:latest",
            [{"role": "user", "content": "hi"}],
            timeout_s=5,
            api_key="wrong",
        )


async def test_a_404_points_at_the_address_and_the_protocol(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The likeliest hosted misconfiguration is an OpenAI-compatible endpoint,
    which answers /v1/chat/completions and has no /api/chat at all."""
    _install(monkeypatch, lambda request: httpx.Response(404, text="not found"))

    with pytest.raises(OllamaChatError, match="OpenAI-compatible"):
        await chat(
            "https://gw.example.com/v1",
            "qwen3:latest",
            [{"role": "user", "content": "hi"}],
            timeout_s=5,
        )


async def test_the_probe_reports_a_rejected_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    """ "Test connection" is the one place an operator looks when a hosted
    endpoint will not work. A 401 collapsing to "no version" made it print the
    install hint — "install Ollama, then ollama pull qwen3" — for a server that
    was running fine and simply refused the token."""
    _install(monkeypatch, lambda request: httpx.Response(401, json={"error": "unauthorized"}))

    probe = await ollama_probe({OLLAMA_HOST_ENV: "https://gw.example.com", "OLLAMA_API_KEY": "x"})

    assert probe.version is None
    assert probe.error is not None
    assert "rejected the credential" in probe.error


async def test_the_probe_reports_an_absent_server_without_inventing_a_reason(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No answer at all carries no extra advice, so the caller falls back to the
    install hint — which is the right message in exactly that case."""

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    _install(monkeypatch, refuse)

    probe = await ollama_probe({OLLAMA_HOST_ENV: "http://localhost:11434"})

    assert probe.version is None
    assert probe.error is None


async def test_the_probe_returns_the_version_when_the_server_answers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install(monkeypatch, lambda request: httpx.Response(200, json={"version": "0.5.7"}))

    probe = await ollama_probe({OLLAMA_HOST_ENV: "https://gw.example.com/ollama"})

    assert probe == ProbeResult("Ollama 0.5.7", None)


def test_probe_and_list_share_the_header_builder() -> None:
    """Guards against one path growing auth while the other silently does not."""
    assert ollama_models.auth_headers(" tok ") == {"Authorization": "Bearer tok"}
    assert ollama_models.auth_headers("") == {}
    assert ollama_models.auth_headers(None) == {}
