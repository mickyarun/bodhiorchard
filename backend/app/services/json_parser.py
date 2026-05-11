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
from typing import Any

from pydantic import BaseModel, ValidationError


class ChatAIResponse(BaseModel):
    """Expected schema for chat AI responses."""

    reply: str
    updated_content: str | None = None


def parse_json_response(output: str) -> dict[str, Any] | None:
    """Parse an AI response that should contain a JSON object.

    Tries three strategies in order:
    1. Direct JSON parse of the trimmed output.
    2. Extract from a ```json markdown code fence.
    3. Extract the first top-level ``{...}`` block.

    Args:
        output: Raw text output from the AI model.

    Returns:
        Parsed dict if JSON was found, else None.
    """
    text = output.strip()

    # 1. Direct JSON
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. Markdown code fence
    if "```json" in text:
        try:
            start = text.index("```json") + 7
            end = text.index("```", start)
            return json.loads(text[start:end].strip())
        except (json.JSONDecodeError, ValueError):
            pass

    # 3. First {...} block
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end > brace_start:
        try:
            return json.loads(text[brace_start : brace_end + 1])
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
