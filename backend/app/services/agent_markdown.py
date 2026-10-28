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

"""Clean agent prose before it is stored as a BUD markdown section.

A stage agent's final message is meant to be the document itself, but the
model often wraps it in chat: a "Here's the draft tech spec:" lead-in, and
— when the host's output-style plugins leak into the subprocess — ``★
Insight`` blocks. Both end up verbatim in the saved section unless the
result handler removes them.
"""

import re

from app.services.json_parser import strip_insight_blocks

# Opening/closing line of a fenced code block (``` or ~~~, up to 3 spaces
# of indent per CommonMark). A ``# `` line inside a fence is a shell or
# Python comment, not a heading.
_FENCE_RE = re.compile(r"^ {0,3}(```|~~~)")
_H1_RE = re.compile(r"^# \S")
_SUBHEADING_RE = re.compile(r"^#{2,6} \S")


def strip_chat_preamble(text: str) -> str:
    """Drop chat lead-in before the document's top-level ``# `` heading.

    Only text that reads as lead-in is dropped: if a ``##``-or-deeper
    heading comes before the first ``# `` line, the document had already
    started (the model skipped its title, and the ``# `` line is a level
    slip or prose like "# of retries…"), so ``text`` is returned unchanged.
    Same when there is no top-level heading outside a code fence — without
    one there is no reliable boundary, and dropping real content is worse
    than keeping a stray sentence.
    """
    in_fence = False
    offset = 0
    for line in text.splitlines(keepends=True):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
        elif not in_fence and _SUBHEADING_RE.match(line):
            return text
        elif not in_fence and _H1_RE.match(line):
            return text[offset:]
        offset += len(line)
    return text


def strip_insights(text: str) -> str:
    """Return ``text`` without insight blocks, trimmed."""
    without_insights, _ = strip_insight_blocks(text)
    return without_insights.strip()


def clean_agent_markdown(text: str) -> str:
    """Return ``text`` without insight blocks or a chat lead-in, trimmed.

    For documents whose format opens with a ``# `` title (the tech spec).
    Formats without one should use :func:`strip_insights` alone.
    """
    return strip_chat_preamble(strip_insights(text)).strip()


__all__ = ["clean_agent_markdown", "strip_chat_preamble", "strip_insights"]
