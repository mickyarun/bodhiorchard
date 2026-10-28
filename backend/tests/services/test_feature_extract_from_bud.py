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

"""Turning a BUD title and requirements into a planned feature summary (pure parsing)."""

from __future__ import annotations

import pytest

from app.services.feature_lifecycle import extract_feature_from_bud


@pytest.mark.parametrize(
    ("title", "name"),
    [
        ("BUD: Gift cards", "Gift cards"),
        ("prd - Gift cards", "Gift cards"),
        ("Feature — Gift cards", "Gift cards"),
        ("RFC:Gift cards", "Gift cards"),
        ("Gift cards", "Gift cards"),
        ("BUD:", "BUD:"),
    ],
)
def test_the_name_drops_a_document_prefix(title: str, name: str) -> None:
    assert extract_feature_from_bud(title, "").name == name


def test_the_description_is_the_first_plain_paragraph_capped_at_300() -> None:
    md = "# Title\n\n---\n\n" + "x" * 400 + "\n\nSecond paragraph"
    assert extract_feature_from_bud("T", md).description == "x" * 300


def test_capabilities_come_from_the_criteria_section_only_and_stop_at_six() -> None:
    bullets = "\n".join(f"- cap {i}" for i in range(9))
    md = f"- not a capability\n\n## Acceptance Criteria\n{bullets}\n"
    assert extract_feature_from_bud("T", md).capabilities == [f"cap {i}" for i in range(6)]


def test_capabilities_end_at_the_next_heading_and_skip_empty_bullets() -> None:
    md = "### Requirements\n* first\n- \n- second\n## Out of scope\n- not this\n"
    assert extract_feature_from_bud("T", md).capabilities == ["first", "second"]


def test_tags_are_lowercase_title_words_without_stop_words_capped_at_five() -> None:
    summary = extract_feature_from_bud(
        "BUD: The Search and Filter for Orders by Date with Paging Support", ""
    )
    assert summary.tags == ["search", "filter", "orders", "date", "paging"]


def test_empty_requirements_give_an_empty_summary_body() -> None:
    summary = extract_feature_from_bud("Café checkout ☕", "")
    assert summary.name == "Café checkout ☕"
    assert summary.description == ""
    assert summary.capabilities == []
