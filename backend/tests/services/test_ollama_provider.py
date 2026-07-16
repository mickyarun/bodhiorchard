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

"""The Ollama provider: single-shot calls and the in-process tool loop."""

import json
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.models.organization import AIProvider
from app.services.ai_runner.ollama_chat import OllamaChatError
from app.services.ai_runner.ollama_models import (
    OLLAMA_HOST_ENV,
    OLLAMA_MODEL_ENV,
    OLLAMA_THINK_ENV,
)
from app.services.ai_runner.ollama_provider import OllamaProvider
from app.services.ai_runner.registry import provider_instance
from app.services.claude_runner import (
    NO_REPO_CONTEXT,
    ClaudeRunnerConfig,
    MCPServerConfig,
)

ORG_ID = str(uuid.uuid4())
_SENTINEL: Any = object()


def _cfg(**kw: Any) -> ClaudeRunnerConfig:
    # env_extra is what adapt_config fills in from the org — the model included.
    env = {
        OLLAMA_HOST_ENV: "http://ollama-host:11434",
        OLLAMA_THINK_ENV: "0",
        OLLAMA_MODEL_ENV: "qwen3:latest",
    }
    env.update(kw.pop("env", {}))
    return ClaudeRunnerConfig(env_extra=env, **kw)


def _mcp(tools: list[str] | None = None) -> MCPServerConfig:
    return MCPServerConfig(
        backend_url="http://b",
        mcp_token="t",
        tool_names=tools if tools is not None else ["get_features"],
        org_id=ORG_ID,
    )


def _msg(content: str = "", tool_calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    msg: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    return msg


def _call(name: str, **args: Any) -> dict[str, Any]:
    return {"function": {"name": name, "arguments": args}}


@contextmanager
def _fake_org_lookup(org: object | None = _SENTINEL) -> Iterator[None]:
    """Stand in for the loop's own session and org lookup.

    The loop opens its own session — it cannot borrow a request's — so both
    are patched. Pass ``None`` to simulate an org that no longer exists.
    """
    resolved = SimpleNamespace(id=uuid.UUID(ORG_ID)) if org is _SENTINEL else org
    repo = MagicMock()
    repo.return_value.get_by_id = AsyncMock(return_value=resolved)
    with (
        patch("app.services.ai_runner.ollama_provider.AsyncSessionLocal"),
        patch("app.services.ai_runner.ollama_provider.OrganizationRepository", repo),
    ):
        yield


# --- the registry must not route Ollama anywhere else -------------------------


def test_ollama_gets_its_own_adapter() -> None:
    """A local-only provider silently running on a hosted API is the worst bug
    available here: it succeeds, bills, and ships prompts off the machine."""
    assert isinstance(provider_instance(AIProvider.ollama), OllamaProvider)


# --- single shot (the pure-LLM callers) --------------------------------------


async def test_single_shot_sends_the_org_host_and_thinking_setting() -> None:
    chat = AsyncMock(return_value=_msg("BODHIORCHARD_CONNECTION_OK"))
    with patch("app.services.ai_runner.ollama_provider.chat", chat):
        result = await OllamaProvider().run(
            "ping", NO_REPO_CONTEXT, _cfg(env={OLLAMA_THINK_ENV: "1"})
        )
    assert result.success and result.output == "BODHIORCHARD_CONNECTION_OK"
    args, kwargs = chat.await_args
    assert args[0] == "http://ollama-host:11434"  # the org's host, not a global default
    assert args[1] == "qwen3:latest"
    assert kwargs["think"] is True
    assert kwargs.get("tools") is None  # no MCP config -> no tools offered


async def test_thinking_off_unless_enabled() -> None:
    """Off is the decided default; only an explicit "1" turns it on."""
    chat = AsyncMock(return_value=_msg("x"))
    with patch("app.services.ai_runner.ollama_provider.chat", chat):
        await OllamaProvider().run("p", NO_REPO_CONTEXT, _cfg())
    assert chat.await_args.kwargs["think"] is False


async def test_json_format_requested_for_json_callers() -> None:
    """Six callers parse strict JSON behind a fallback; constraining the output
    makes the good path far likelier on a small model."""
    chat = AsyncMock(return_value=_msg('{"a":1}'))
    with patch("app.services.ai_runner.ollama_provider.chat", chat):
        await OllamaProvider().run("p", NO_REPO_CONTEXT, _cfg(output_format="json"))
    assert chat.await_args.kwargs["json_format"] is True


async def test_no_model_fails_with_a_usable_message() -> None:
    """The valid ids live on the user's host, so guessing one would fail later
    and further from the cause."""
    result = await OllamaProvider().run(
        "p", NO_REPO_CONTEXT, ClaudeRunnerConfig(model="", env_extra={})
    )
    assert result.success is False
    assert result.error and "AI Config" in result.error


async def test_a_skills_claude_model_is_never_sent_to_ollama() -> None:
    """Every skill's frontmatter names a Claude tier — `sonnet`, `haiku`.

    Those are another provider's vocabulary. Passing one through would make
    Ollama 404 on the first message of every reachable feature, so the org's
    own choice wins and the skill's id is ignored.
    """
    chat = AsyncMock(return_value=_msg("ok"))
    with patch("app.services.ai_runner.ollama_provider.chat", chat):
        await OllamaProvider().run("p", NO_REPO_CONTEXT, _cfg(model="sonnet"))
    assert chat.await_args.args[1] == "qwen3:latest"


async def test_no_org_model_fails_rather_than_guessing() -> None:
    """With no org model there is nothing safe to fall back to."""
    result = await OllamaProvider().run(
        "p",
        NO_REPO_CONTEXT,
        ClaudeRunnerConfig(model="sonnet", env_extra={OLLAMA_HOST_ENV: "http://h:11434"}),
    )
    assert result.success is False
    assert result.error and "model" in result.error.lower()


async def test_unreachable_host_fails_the_run_not_the_process() -> None:
    with patch(
        "app.services.ai_runner.ollama_provider.chat",
        AsyncMock(side_effect=OllamaChatError("Cannot reach Ollama at http://x")),
    ):
        result = await OllamaProvider().run("p", NO_REPO_CONTEXT, _cfg())
    assert result.success is False
    assert result.error and "Cannot reach Ollama" in result.error


# --- the tool loop -----------------------------------------------------------


async def test_tool_call_runs_in_process_and_feeds_the_result_back() -> None:
    """The keystone: model asks for a tool, we run it here, it answers."""
    chat = AsyncMock(
        side_effect=[
            _msg(tool_calls=[_call("get_features", repo="bodhi")]),
            _msg("There are 3 features."),
        ]
    )
    dispatch = AsyncMock(return_value=json.dumps({"features": ["a", "b", "c"]}))
    progress: list[str] = []
    with (
        patch("app.services.ai_runner.ollama_provider.chat", chat),
        patch("app.services.ai_runner.ollama_tools.dispatch_tool", dispatch),
        _fake_org_lookup(),
    ):
        result = await OllamaProvider().run(
            "how many features?",
            NO_REPO_CONTEXT,
            _cfg(mcp=_mcp()),
            lambda name, _: progress.append(name),
        )
    assert result.success and result.output == "There are 3 features."
    assert dispatch.await_args.args[2] == "get_features"
    assert dispatch.await_args.args[3] == {"repo": "bodhi"}
    # The second call must carry the tool result back, or the model answers blind.
    second_messages = chat.await_args_list[1].args[2]
    assert second_messages[-1]["role"] == "tool"
    assert "features" in second_messages[-1]["content"]
    # Timelines animate off this.
    assert progress == ["get_features"]


async def test_only_requested_tools_are_offered() -> None:
    """29 tools with long descriptions is a lot of ways for a small model to
    pick wrong, so callers name what they need."""
    chat = AsyncMock(return_value=_msg("done"))
    with (
        patch("app.services.ai_runner.ollama_provider.chat", chat),
        _fake_org_lookup(),
    ):
        await OllamaProvider().run("q", NO_REPO_CONTEXT, _cfg(mcp=_mcp(["get_features"])))
    offered = {t["function"]["name"] for t in chat.await_args.kwargs["tools"]}
    assert offered == {"get_features"}


async def test_loop_that_never_answers_fails_loudly() -> None:
    """A model stuck calling tools must not have its last tool result returned
    as though it were an answer."""
    chat = AsyncMock(return_value=_msg(tool_calls=[_call("get_features", repo="x")]))
    with (
        patch("app.services.ai_runner.ollama_provider.chat", chat),
        patch("app.services.ai_runner.ollama_tools.dispatch_tool", AsyncMock(return_value="{}")),
        _fake_org_lookup(),
    ):
        result = await OllamaProvider().run("q", NO_REPO_CONTEXT, _cfg(mcp=_mcp(), max_turns=3))
    assert result.success is False
    assert result.error and "without answering" in result.error
    assert chat.await_count == 3  # capped, not runaway


async def test_a_tool_run_naming_no_tools_refuses() -> None:
    """The CLI reads an empty tool list as "expose everything"; a caller
    written against that meaning must not silently get a model with no tools.

    For agents whose output is entirely MCP side effects, that reads as a
    clean success while nothing was written — the PRD agent would report
    "drafted" against an untouched BUD.
    """
    chat = AsyncMock(return_value=_msg("here is some prose"))
    with (
        patch("app.services.ai_runner.ollama_provider.chat", chat),
        _fake_org_lookup(),
    ):
        result = await OllamaProvider().run("q", NO_REPO_CONTEXT, _cfg(mcp=_mcp([])))
    assert result.success is False
    assert result.error and "did not name the MCP tools" in result.error
    chat.assert_not_awaited()  # never asked the model at all


async def test_mcp_config_without_an_org_refuses() -> None:
    """Running an org's tools against the wrong org — or none — is worse than
    failing."""
    mcp = MCPServerConfig(backend_url="http://b", mcp_token="t", tool_names=["get_features"])
    result = await OllamaProvider().run("q", NO_REPO_CONTEXT, _cfg(mcp=mcp))
    assert result.success is False
    assert result.error and "organisation" in result.error.lower()


@pytest.mark.parametrize("bad", [None, "not-a-dict", 42])
async def test_malformed_tool_calls_do_not_crash_the_run(bad: Any) -> None:
    """Never trust the shape a model returns."""
    chat = AsyncMock(side_effect=[_msg(tool_calls=[bad]), _msg("recovered")])
    with (
        patch("app.services.ai_runner.ollama_provider.chat", chat),
        _fake_org_lookup(),
    ):
        result = await OllamaProvider().run("q", NO_REPO_CONTEXT, _cfg(mcp=_mcp()))
    assert result.success and result.output == "recovered"
