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

"""A wireframe answered as prose must not be thrown away.

The designer persists via write_bud_design; a model that answers with the HTML
and skips the tool leaves job_design reporting "Agent did not call
write_bud_design MCP" while the document it authored is discarded. The recovery
must be precise: a real document is stored through the tool's own handler, and
anything ambiguous is left alone so an explanatory snippet is never mistaken for
the wireframe.
"""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.design_output_fallback import (
    extract_wireframe_html,
    save_wireframe_from_output,
)

_MOD = "app.services.design_output_fallback"
DOC = "<!DOCTYPE html>\n<html><body><h1>Wireframe</h1></body></html>"


def test_extracts_an_html_fence() -> None:
    assert extract_wireframe_html(f"Here it is:\n```html\n{DOC}\n```") == DOC


def test_extracts_a_bare_document_and_drops_surrounding_chatter() -> None:
    """Models bracket the document with prose; only the document is the artifact."""
    assert extract_wireframe_html(f"Sure!\n{DOC}\nHope that helps!") == DOC


def test_returns_none_for_prose_with_no_document() -> None:
    assert extract_wireframe_html("I was unable to produce a wireframe.") is None


def test_returns_none_for_a_loose_fragment() -> None:
    """A bare <div> is not an unambiguous artifact — storing it as the wireframe
    would be worse than reporting the miss."""
    assert extract_wireframe_html("Use a <div class='card'>card</div> here.") is None


@pytest.mark.parametrize(
    "refusal",
    [
        "I started an <html> skeleton but ran out of context. Please retry.",
        "I cannot generate this. A wireframe would start with <!DOCTYPE html> and go from there.",
    ],
)
def test_refusal_that_merely_mentions_html_is_never_stored(refusal: str) -> None:
    """Nothing downstream re-checks the shape: a stored refusal would be marked
    READY and shown to the user as a finished design, with no error anywhere.
    Rejecting it is strictly better than the miss it would replace."""
    assert extract_wireframe_html(refusal) is None


def test_truncated_document_without_a_closing_tag_is_rejected() -> None:
    assert extract_wireframe_html("<!DOCTYPE html>\n<html><body><h1>Half a wire") is None


def test_fenced_fragment_is_rejected() -> None:
    """A model explaining a snippet inside an html fence is common."""
    assert extract_wireframe_html("Add this:\n```html\n<div class='card'>x</div>\n```") is None


def test_two_documents_are_ambiguous_and_rejected() -> None:
    """A before/after reply — picking either one is a coin flip."""
    output = f"The old one:\n{DOC}\nand the new one:\n{DOC}"
    assert extract_wireframe_html(output) is None


def test_closing_tag_inside_a_script_string_does_not_truncate() -> None:
    """The last closing tag wins, so an in-script '</html>' is not the end."""
    doc = "<!DOCTYPE html>\n<html><body><script>var s='</html>';</script></body></html>"
    assert extract_wireframe_html(doc) == doc


async def _save(output: str, handler_result: dict) -> tuple[bool, MagicMock]:
    handler = AsyncMock(return_value=handler_result)
    with (
        patch(
            f"{_MOD}.AsyncSessionLocal",
            MagicMock(return_value=_AsyncCM(MagicMock())),
        ),
        patch(
            f"{_MOD}.OrganizationRepository",
            return_value=MagicMock(get_by_id=AsyncMock(return_value=MagicMock())),
        ),
        patch(f"{_MOD}.handle_write_bud_design", handler),
    ):
        saved = await save_wireframe_from_output(
            output,
            org_id=uuid.uuid4(),
            bud_id=str(uuid.uuid4()),
            design_id=str(uuid.uuid4()),
            repo_id=None,
        )
    return saved, handler


class _AsyncCM:
    def __init__(self, value: object) -> None:
        self._value = value

    async def __aenter__(self) -> object:
        return self._value

    async def __aexit__(self, *_: object) -> bool:
        return False


@pytest.mark.asyncio
async def test_persists_through_the_tools_own_handler() -> None:
    """Reuse keeps sanitisation, READY marking and the timeline event identical."""
    saved, handler = await _save(f"```html\n{DOC}\n```", {"success": True})

    assert saved is True
    params = handler.await_args.args[2]
    assert params["html"] == DOC
    # The design_id path verifies the row belongs to this BUD before mutating.
    assert "design_id" in params and "bud_id" in params


@pytest.mark.asyncio
async def test_reports_miss_when_there_is_no_document_to_recover() -> None:
    saved, handler = await _save("Sorry, no design.", {"success": True})

    assert saved is False
    handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_rejected_write_is_not_reported_as_saved() -> None:
    """The handler rejects a bud/design mismatch — that must stay a failure."""
    saved, _ = await _save(f"```html\n{DOC}\n```", {"success": False, "error": "not found"})

    assert saved is False
