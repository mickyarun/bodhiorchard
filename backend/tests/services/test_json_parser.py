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

"""Tests for the AI-response JSON extractor.

Specifically targets the log-line leak from the production bug: a real
reply followed by a structlog ``{...}`` event used to be merged into a
single object by the old ``find('{') ... rfind('}')`` slice. The
brace-balanced first-object scanner must return *only* the first
object and ignore everything after.
"""

from __future__ import annotations

from app.services.json_parser import (
    _extract_first_balanced_object,
    parse_chat_response,
    parse_json_response,
)


def test_direct_parse_returns_dict() -> None:
    """A clean JSON object parses directly."""
    out = parse_json_response('{"reply": "hi"}')
    assert out == {"reply": "hi"}


def test_fenced_block_takes_precedence_over_prose() -> None:
    """``\\`\\`\\`json ... \\`\\`\\``` fence is preferred over the brace scanner."""
    text = 'Some preamble\n```json\n{"reply": "hi", "updated_content": null}\n```\nTrailing prose.'
    out = parse_json_response(text)
    assert out == {"reply": "hi", "updated_content": None}


def test_first_balanced_object_when_followed_by_log_line() -> None:
    """Reply object + trailing structlog event → only the first object is returned.

    Regression test for the bug where ``{"reply":"hi"}\\n{"event":"x"}``
    was glued into a single broken JSON span by the old ``rfind('}')``.
    """
    text = '{"reply": "hi"}\n{"event": "claude_run_complete", "ok": true}'
    out = parse_json_response(text)
    assert out == {"reply": "hi"}


def test_brace_inside_string_literal_does_not_close_object() -> None:
    """A literal ``}`` inside a string must not be treated as the closer."""
    candidate = _extract_first_balanced_object('{"reply": "with a } in it", "x": 1} junk')
    assert candidate == '{"reply": "with a } in it", "x": 1}'


def test_escaped_quote_inside_string_does_not_break_state() -> None:
    """``\\"`` escapes are honoured by the scanner."""
    text = '{"reply": "she said \\"hi\\"", "x": 2}'
    out = parse_json_response(text)
    assert out == {"reply": 'she said "hi"', "x": 2}


def test_returns_none_when_no_brace_present() -> None:
    """Pure prose with no JSON → ``None``."""
    assert parse_json_response("not-json-at-all") is None


def test_returns_none_when_only_unbalanced_braces() -> None:
    """Open brace with no matching close → ``None``, not a partial parse."""
    assert parse_json_response("text { incomplete") is None


def test_returns_none_when_first_object_is_invalid_json() -> None:
    """First balanced span fails ``json.loads`` → ``None``.

    Crucially, the scanner does NOT then walk forward looking for a
    second candidate — that would re-introduce the leak.
    """
    assert parse_json_response('{not: "valid"} {"reply": "ok"}') is None


def test_parse_chat_response_validates_schema() -> None:
    """``parse_chat_response`` rejects objects without ``reply``."""
    assert parse_chat_response('{"foo": "bar"}') is None
    out = parse_chat_response('{"reply": "ok"}')
    assert out is not None and out.reply == "ok"


def test_parse_chat_response_rejects_log_line_after_reply() -> None:
    """The leak scenario, end-to-end: validated reply is just ``reply``."""
    text = '{"reply": "Done", "updated_content": null}\n{"event": "claude_stream_finished"}'
    out = parse_chat_response(text)
    assert out is not None
    assert out.reply == "Done"
    assert out.updated_content is None


def test_extract_first_balanced_object_handles_nested_objects() -> None:
    """Nested ``{...}`` braces are tracked by depth."""
    candidate = _extract_first_balanced_object('{"a": {"b": {"c": 1}}, "d": 2} trailing')
    assert candidate == '{"a": {"b": {"c": 1}}, "d": 2}'
