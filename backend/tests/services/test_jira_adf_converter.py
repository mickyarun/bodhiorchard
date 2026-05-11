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

"""Unit tests for the Jira ADF-to-Markdown converter.

Pure-function tests — no database, no HTTP, no fixtures.
Tests every supported ADF node type and common edge cases.
"""

import pytest

from app.services.jira_adf_converter import adf_to_markdown


class TestBasicConversion:
    """Core conversion behaviour for simple documents."""

    def test_none_input(self) -> None:
        assert adf_to_markdown(None) == ""

    def test_empty_doc(self) -> None:
        assert adf_to_markdown({"type": "doc", "content": []}) == ""

    def test_wrong_root_type(self) -> None:
        assert adf_to_markdown({"type": "paragraph", "content": []}) == ""

    def test_plain_paragraph(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "Hello world"}],
                }
            ],
        }
        assert adf_to_markdown(doc) == "Hello world"

    def test_multiple_paragraphs(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {"type": "paragraph", "content": [{"type": "text", "text": "First"}]},
                {"type": "paragraph", "content": [{"type": "text", "text": "Second"}]},
            ],
        }
        assert adf_to_markdown(doc) == "First\n\nSecond"


class TestInlineMarks:
    """Text marks: bold, italic, code, strikethrough, link."""

    def test_bold(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "bold", "marks": [{"type": "strong"}]}],
                }
            ],
        }
        assert adf_to_markdown(doc) == "**bold**"

    def test_italic(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "italic", "marks": [{"type": "em"}]}],
                }
            ],
        }
        assert adf_to_markdown(doc) == "*italic*"

    def test_inline_code(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "code", "marks": [{"type": "code"}]}],
                }
            ],
        }
        assert adf_to_markdown(doc) == "`code`"

    def test_strikethrough(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": "old", "marks": [{"type": "strike"}]}],
                }
            ],
        }
        assert adf_to_markdown(doc) == "~~old~~"

    def test_link(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "click",
                            "marks": [{"type": "link", "attrs": {"href": "https://x.com"}}],
                        }
                    ],
                }
            ],
        }
        assert adf_to_markdown(doc) == "[click](https://x.com)"

    def test_nested_marks(self) -> None:
        """Bold + italic applied to same text."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {
                            "type": "text",
                            "text": "both",
                            "marks": [{"type": "strong"}, {"type": "em"}],
                        }
                    ],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "**" in result
        assert "*" in result
        assert "both" in result

    def test_mixed_inline(self) -> None:
        """Paragraph with plain + bold + plain text nodes."""
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Hello "},
                        {"type": "text", "text": "world", "marks": [{"type": "strong"}]},
                        {"type": "text", "text": "!"},
                    ],
                }
            ],
        }
        assert adf_to_markdown(doc) == "Hello **world**!"


class TestHeadings:
    """Heading levels 1-6."""

    @pytest.mark.parametrize("level", [1, 2, 3, 4, 5, 6])
    def test_heading_levels(self, level: int) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "heading",
                    "attrs": {"level": level},
                    "content": [{"type": "text", "text": "Title"}],
                }
            ],
        }
        assert adf_to_markdown(doc) == f"{'#' * level} Title"


class TestLists:
    """Bullet and ordered lists."""

    def test_bullet_list(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "bulletList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "A"}]}
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {"type": "paragraph", "content": [{"type": "text", "text": "B"}]}
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "- A" in result
        assert "- B" in result

    def test_ordered_list(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "orderedList",
                    "content": [
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "First"}],
                                }
                            ],
                        },
                        {
                            "type": "listItem",
                            "content": [
                                {
                                    "type": "paragraph",
                                    "content": [{"type": "text", "text": "Second"}],
                                }
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "1. First" in result
        assert "2. Second" in result


class TestCodeBlock:
    """Code blocks with language."""

    def test_code_block_with_language(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "attrs": {"language": "python"},
                    "content": [{"type": "text", "text": "print('hi')"}],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "```python" in result
        assert "print('hi')" in result
        assert result.endswith("```")

    def test_code_block_no_language(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "codeBlock",
                    "attrs": {},
                    "content": [{"type": "text", "text": "code"}],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert result.startswith("```")
        assert "code" in result


class TestBlockElements:
    """Blockquotes, rules, panels, tables."""

    def test_blockquote(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "blockquote",
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Quoted"}]}
                    ],
                }
            ],
        }
        assert "> Quoted" in adf_to_markdown(doc)

    def test_rule(self) -> None:
        doc = {"type": "doc", "content": [{"type": "rule"}]}
        assert adf_to_markdown(doc) == "---"

    def test_panel_warning(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "panel",
                    "attrs": {"panelType": "warning"},
                    "content": [
                        {"type": "paragraph", "content": [{"type": "text", "text": "Careful"}]}
                    ],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "> **Warning:**" in result
        assert "Careful" in result

    def test_table(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "table",
                    "content": [
                        {
                            "type": "tableRow",
                            "content": [
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "A"}],
                                        }
                                    ],
                                },
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "B"}],
                                        }
                                    ],
                                },
                            ],
                        },
                        {
                            "type": "tableRow",
                            "content": [
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "1"}],
                                        }
                                    ],
                                },
                                {
                                    "type": "tableCell",
                                    "content": [
                                        {
                                            "type": "paragraph",
                                            "content": [{"type": "text", "text": "2"}],
                                        }
                                    ],
                                },
                            ],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "| A | B |" in result
        assert "| --- | --- |" in result
        assert "| 1 | 2 |" in result


class TestInlineElements:
    """Mentions, emoji, hardBreak, inlineCard, status."""

    def test_mention(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "mention", "attrs": {"text": "Alice"}}],
                }
            ],
        }
        assert "@Alice" in adf_to_markdown(doc)

    def test_emoji(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "emoji", "attrs": {"shortName": ":thumbsup:"}}],
                }
            ],
        }
        assert ":thumbsup:" in adf_to_markdown(doc)

    def test_hard_break(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "text", "text": "Line 1"},
                        {"type": "hardBreak"},
                        {"type": "text", "text": "Line 2"},
                    ],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "Line 1" in result
        assert "Line 2" in result

    def test_inline_card(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [
                        {"type": "inlineCard", "attrs": {"url": "https://jira.example.com/X-1"}}
                    ],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "https://jira.example.com/X-1" in result

    def test_status_badge(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "status", "attrs": {"text": "IN PROGRESS"}}],
                }
            ],
        }
        assert "[IN PROGRESS]" in adf_to_markdown(doc)


class TestTaskList:
    """ADF action items (task lists)."""

    def test_task_list_mixed_states(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "taskList",
                    "content": [
                        {
                            "type": "taskItem",
                            "attrs": {"state": "DONE"},
                            "content": [{"type": "text", "text": "Done task"}],
                        },
                        {
                            "type": "taskItem",
                            "attrs": {"state": "TODO"},
                            "content": [{"type": "text", "text": "Todo task"}],
                        },
                    ],
                }
            ],
        }
        result = adf_to_markdown(doc)
        assert "- [x] Done task" in result
        assert "- [ ] Todo task" in result


class TestUnknownNodes:
    """Graceful handling of unrecognized node types."""

    def test_unknown_node_with_text(self) -> None:
        doc = {
            "type": "doc",
            "content": [
                {
                    "type": "weirdCustomNode",
                    "content": [{"type": "text", "text": "fallback text"}],
                }
            ],
        }
        assert "fallback text" in adf_to_markdown(doc)

    def test_unknown_node_empty(self) -> None:
        doc = {"type": "doc", "content": [{"type": "unknownEmpty"}]}
        # Should not crash
        adf_to_markdown(doc)
