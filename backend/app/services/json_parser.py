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

"""Shared JSON parsing utilities for AI agent responses.

AI models return JSON in various formats (raw, markdown-fenced, embedded
in prose). This module provides a single extractor used by chat handlers,
triage agents, and any future handler that needs to parse LLM output.
"""

import json
from typing import Any, cast

from pydantic import BaseModel, ValidationError


class ChatAIResponse(BaseModel):
    """Expected schema for chat AI responses."""

    reply: str
    updated_content: str | None = None


def _extract_first_balanced_object(text: str) -> str | None:
    """Return the substring of the first balanced top-level ``{...}`` object.

    Walks the string tracking brace depth and string-literal state (with
    escape handling) so a quoted ``}`` inside a string literal does not
    end the object. Returns the substring spanning the first ``{`` and
    its matching ``}``. Returns ``None`` if no balanced object exists.

    This replaces the previous greedy ``find('{') ... rfind('}')`` slice,
    which happily glued a real reply onto a trailing log-line object —
    the bug that put ``{"event": "claude_run_complete", ...}`` into a
    user-facing chat reply.
    """
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            depth += 1
            continue
        if ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return None


def parse_json_response(output: str) -> dict[str, Any] | None:
    """Parse an AI response that should contain a JSON object.

    Tries three strategies in order, stopping at the first that yields a
    valid ``dict``:

    1. Direct ``json.loads`` of the trimmed output.
    2. Extract from a ```` ```json ... ``` ```` markdown code fence.
    3. First **balanced** top-level ``{...}`` object via a single-pass
       brace-depth scanner (see :func:`_extract_first_balanced_object`).

    Returns ``None`` when no strategy succeeds. A caller that observes
    ``None`` must surface a retryable error rather than dumping the raw
    output as a user-facing reply.
    """
    text = output.strip()

    # 1. Direct JSON
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return cast(dict[str, Any], parsed)
    except json.JSONDecodeError:
        pass

    # 2. Markdown code fence
    if "```json" in text:
        try:
            start = text.index("```json") + 7
            end = text.index("```", start)
            parsed = json.loads(text[start:end].strip())
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. First balanced ``{...}`` block — brace-balanced, string-literal aware.
    candidate = _extract_first_balanced_object(text)
    if candidate is not None:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, dict):
                return cast(dict[str, Any], parsed)
        except json.JSONDecodeError:
            pass

    return None


def parse_chat_response(output: str) -> ChatAIResponse | None:
    """Parse and validate an AI chat response against the expected schema.

    Extracts JSON from the raw LLM output, then validates it has the
    required ``reply`` field and optional ``updated_content`` field.
    Rejects responses with unexpected structure.

    Args:
        output: Raw text output from the AI model.

    Returns:
        Validated ChatAIResponse if valid, else None.
    """
    raw = parse_json_response(output)
    if raw is None:
        return None
    try:
        return ChatAIResponse.model_validate(raw)
    except ValidationError:
        return None
