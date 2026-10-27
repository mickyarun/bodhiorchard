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

"""Agent prose is cleaned of chat lead-in and insight blocks before storage."""

from app.services.agent_markdown import clean_agent_markdown, strip_chat_preamble

SPEC = "# BUD-007 — Task tags\n\n## Executive Summary\n\nAdd tags to tasks."
INSIGHT = (
    "`★ Insight ─────────────────────────────────────`\n"
    "- The worker polls Redis.\n"
    "`─────────────────────────────────────────────────`\n"
)


def test_drops_lead_in_before_first_h1() -> None:
    text = f"I've read through all the relevant code.\n\nHere's the draft tech spec:\n\n{SPEC}"
    assert strip_chat_preamble(text) == SPEC


def test_text_without_h1_is_left_alone() -> None:
    """No heading means no safe boundary — keep everything."""
    text = "Intro sentence.\n\n## Problem Statement\n\nBody"
    assert strip_chat_preamble(text) == text


def test_h1_inside_code_fence_is_not_a_boundary() -> None:
    text = f"Run this first:\n\n```bash\n# install deps\nnpm ci\n```\n\n{SPEC}"
    assert strip_chat_preamble(text) == SPEC


def test_hash_line_after_document_started_is_not_a_boundary() -> None:
    """A model that skipped its title has already started the document; a
    later ``# `` line (level slip or prose) must not truncate everything
    above it."""
    text = (
        "## Problem Statement\n\nBell clips.\n\n"
        "# of retries capped at 3 before the toast shows\n\n## Edge Cases\n\nnone"
    )
    assert strip_chat_preamble(text) == text


def test_spec_without_lead_in_is_unchanged() -> None:
    assert strip_chat_preamble(SPEC) == SPEC


def test_clean_removes_insight_blocks_anywhere_and_lead_in() -> None:
    text = f"{INSIGHT}\nHere's the draft:\n\n{SPEC}\n\n{INSIGHT}\n## Risks\n\nNone."
    cleaned = clean_agent_markdown(text)
    assert cleaned.startswith("# BUD-007")
    assert "★ Insight" not in cleaned
    assert "Here's the draft" not in cleaned
    assert cleaned.endswith("## Risks\n\nNone.")
