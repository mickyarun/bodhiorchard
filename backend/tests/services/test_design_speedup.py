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

"""Tests for the design-prompt speedup wiring.

Covers the four observable surfaces of the speedup work:
- ``claude_runner._extract_cache_usage`` reads Anthropic usage blocks.
- ``job_chat._should_resume_session`` caps resume on long histories.
- ``design_system_extractor._extraction_instructions`` mentions the App
  Skeleton section for web platforms (and not for non-web).
- ``chat_prompts.build_design_prompt`` refers to APP-SKELETON markers
  and no longer asks the agent to browse 2–3 source files for style.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from app.services import chat_prompts
from app.services.claude_runner import _coerce_token_count, _extract_cache_usage
from app.services.design_system_extractor import _extraction_instructions
from app.services.job_chat import _should_resume_session
from app.services.platforms import PlatformKind


def test_extract_cache_usage_reads_top_level_usage() -> None:
    """Modern CLI puts ``usage`` directly on the result event."""
    event = {
        "type": "result",
        "usage": {
            "cache_read_input_tokens": 1200,
            "cache_creation_input_tokens": 50,
            "input_tokens": 200,
        },
    }
    assert _extract_cache_usage(event) == (1200, 50)


def test_extract_cache_usage_reads_nested_message_usage() -> None:
    """Older streaming events nest ``usage`` under ``message``."""
    event = {
        "type": "result",
        "message": {"usage": {"cache_read_input_tokens": 800}},
    }
    read, creation = _extract_cache_usage(event)
    assert read == 800
    assert creation is None


def test_extract_cache_usage_returns_none_when_missing() -> None:
    """No usage block — both values are None, not zero (zero would be a lie)."""
    assert _extract_cache_usage({"type": "result"}) == (None, None)


def test_extract_cache_usage_accepts_float_token_counts() -> None:
    """Forward-compat: a JSON number parsed as float still coerces to int."""
    event = {"usage": {"cache_read_input_tokens": 1500.0}}
    read, creation = _extract_cache_usage(event)
    assert read == 1500
    assert creation is None


def test_coerce_token_count_rejects_bool_and_str() -> None:
    """``bool`` is an ``int`` subclass but isn't a token count — reject it."""
    assert _coerce_token_count(True) is None
    assert _coerce_token_count("1200") is None
    assert _coerce_token_count(None) is None


def test_should_resume_session_allows_short_history() -> None:
    history = [{"role": "user", "content": "small"}] * 5
    assert _should_resume_session(history) is True


def test_should_resume_session_allows_empty_history() -> None:
    """First iteration — no history yet. Resume is still valid (no-op)."""
    assert _should_resume_session(None) is True
    assert _should_resume_session([]) is True


def test_should_resume_session_blocks_long_message_count() -> None:
    history = [{"role": "user", "content": "x"}] * 100
    assert _should_resume_session(history) is False


def test_should_resume_session_blocks_large_byte_count() -> None:
    """Even a short message count blocks if total bytes exceed the cap."""
    history = [{"role": "user", "content": "x" * 60_000}] * 3
    assert _should_resume_session(history) is False


def _fake_platform(kind: PlatformKind) -> SimpleNamespace:
    """Build a minimal stand-in for the Platform protocol.

    ``_extraction_instructions`` only reads ``platform.kind`` and (for
    non-web) interpolates ``platform.kind.value`` — so a SimpleNamespace
    duck-types fine. Avoids depending on a specific concrete impl in
    ``app/services/platforms/``.
    """
    return SimpleNamespace(kind=kind)


def test_extraction_instructions_web_includes_app_skeleton() -> None:
    instructions = _extraction_instructions(_fake_platform(PlatformKind.WEB))
    assert "App Skeleton" in instructions
    assert "APP-SKELETON-BEGIN" in instructions
    assert "APP-SKELETON-END" in instructions


def test_extraction_instructions_non_web_omits_app_skeleton() -> None:
    """Mobile / native repos don't get HTML skeletons — wireframes are web-only."""
    instructions = _extraction_instructions(_fake_platform(PlatformKind.MOBILE_CROSS))
    assert "App Skeleton" not in instructions
    assert "APP-SKELETON-BEGIN" not in instructions


@pytest.mark.asyncio
async def test_build_design_prompt_references_skeleton_and_drops_browse() -> None:
    """The per-BUD prompt must point at the cached skeleton and stop
    asking the agent to browse source files for general visual style.

    The "browse 2-3 files for visual style" instruction was the dominant
    per-BUD latency cost — its removal is the contract this test guards.
    """

    async def _no_links(_org_id: str, _bud_id: str) -> str:
        return ""

    with patch.object(chat_prompts, "_build_design_linked_section", _no_links):
        prompt = await chat_prompts.build_design_prompt(
            bud_ref="BUD-001",
            title="Add task filter",
            org_id="11111111-1111-1111-1111-111111111111",
            message="Make the header darker",
            bud_id="22222222-2222-2222-2222-222222222222",
            repo_id="33333333-3333-3333-3333-333333333333",
        )

    assert "APP-SKELETON-BEGIN" in prompt
    assert "extend that skeleton" in prompt
    assert "Parallelize fetches" in prompt
    # The redundant "browse 2-3 files for style" step must be gone — that
    # generic discovery was the main per-BUD slowdown.
    assert "Read 2–3 existing source files" not in prompt
    assert "Read 2-3 existing source files" not in prompt
