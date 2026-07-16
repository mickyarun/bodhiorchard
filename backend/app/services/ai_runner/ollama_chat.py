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

"""Thin HTTP client for Ollama's /api/chat.

Owns the wire format and nothing else — the tool loop lives in
``ollama_provider``. Non-streaming: we need the whole message (including any
``tool_calls``) before deciding what to do next, so there is nothing to gain
from streaming here.
"""

from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Keeps the model resident between the turns of a tool loop. Without it a cold
# reload can cost more than the inference, and a loop pays that every turn.
_KEEP_ALIVE = "5m"


class OllamaChatError(RuntimeError):
    """Ollama refused or could not answer the request."""


async def chat(
    base_url: str,
    model: str,
    messages: list[dict[str, Any]],
    *,
    timeout_s: float,
    think: bool = False,
    tools: list[dict[str, Any]] | None = None,
    json_format: bool = False,
) -> dict[str, Any]:
    """POST one /api/chat turn and return the assistant message.

    ``think`` is the org's setting, not a constant: reasoning roughly doubles
    latency, which matters most on the CPU-only hosts this targets, but it can
    help the harder structured tasks — so the choice belongs to the operator.

    Raises ``OllamaChatError`` on any failure; the caller decides whether that
    fails the run. Never returns a partial or invented message.
    """
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": think,
        "keep_alive": _KEEP_ALIVE,
    }
    if tools:
        payload["tools"] = tools
    if json_format:
        payload["format"] = "json"

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            resp = await client.post(f"{base_url.rstrip('/')}/api/chat", json=payload)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPStatusError as exc:
        # Ollama rejects a request carrying tools when the model cannot do
        # them, so say that plainly rather than surfacing a bare 400.
        detail = f"HTTP {exc.response.status_code}"
        if tools and exc.response.status_code == 400:
            detail += f" — {model} may not support tool calling"
        raise OllamaChatError(f"Ollama rejected the request: {detail}") from exc
    except (httpx.HTTPError, OSError) as exc:
        raise OllamaChatError(f"Cannot reach Ollama at {base_url}: {exc}") from exc
    except ValueError as exc:
        raise OllamaChatError(f"Ollama returned malformed JSON: {exc}") from exc

    message = body.get("message") if isinstance(body, dict) else None
    if not isinstance(message, dict):
        raise OllamaChatError("Ollama returned no message")
    return message
